"""proofgate.core -- the write-side proof gate.

An AI agent that can mark its own task "done" can also lie about it. This
module is the check that sits between "agent says it's done" and "state
actually changes": no evidence artifact, no completion.

Extracted from a production gate that closed a real hole -- a task tracker
where executors flipped rows to completed while the referenced proof file
was never written, was a stub, or was off-topic for the task. The read-side
verifier that used to catch this was retired; this closes the hole on the
WRITE side instead:

    artifact to disk FIRST -> passes every anchor law -> only THEN the
    caller is allowed to flip state. No pass, no completion.

Anchor laws (a completion is refused unless ALL hold):
  L1  proof path is a real filesystem path (not prose, not a URL)
  L2  the file exists on disk after the write
  L3  body size > MIN_PROOF_BYTES  (kills the 9-byte "exit=0" stub)
  L4  quality_score is non-null and >= MIN_QUALITY_SCORE
  L5  >= 1 of the task's first N significant tokens appears in the artifact
      body (catches proof pasted from a different, unrelated task)
"""
from __future__ import annotations

import os
import re
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

MIN_PROOF_BYTES = 100  # anchor law 3: strictly greater than
MIN_QUALITY_SCORE = 7  # anchor law 4: non-null AND >= this
ITEM_TOKEN_SAMPLE = 8  # anchor law 5: "N/8 item tokens" window

# The artifact's own header (written by write_proof_first) carries the task
# text and would otherwise satisfy both the size floor and the topical check
# on its own. Everything after this marker is the caller's real output and
# is what L3/L5 are measured against.
BODY_MARKER = "<!-- proof-body -->"

_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "into", "your", "then",
    "when", "what", "which", "have", "has", "was", "were", "will", "should",
    "must", "not", "any", "all", "are", "but", "its", "it's", "row", "task",
    "make", "sure", "also", "than", "them", "they", "there", "their", "been",
    "over", "only", "each", "same", "such", "more", "most", "just",
}


class ProofRefused(Exception):
    """Raised when a completion fails one or more anchor laws."""


def looks_like_path(raw) -> bool:
    """Anchor law 1. Prose pasted into a path field is the #1 fake proof."""
    if raw is None:
        return False
    p = str(raw).strip()
    if not p or len(p) > 400 or "\n" in p:
        return False
    if p.lower().startswith(("http://", "https://")):
        return False
    if p.count(" ") > 2 or re.search(r"[;:]\s", p) or p.count(".") > 6:
        return False
    return bool(re.search(r"[\\/]", p)) and bool(re.search(r"\.[A-Za-z0-9]{1,6}$", p))


def proof_body(local_path) -> str:
    """Artifact text with the wrapper's own header stripped."""
    try:
        text = Path(local_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text.split(BODY_MARKER, 1)[1] if BODY_MARKER in text else text


def classify_proof_path(raw):
    """-> (verdict, size_bytes). verdict in
    ok | no_path | not_a_path | missing | tiny"""
    if raw is None or not str(raw).strip():
        return "no_path", 0
    if not looks_like_path(raw):
        return "not_a_path", 0
    local = str(raw)
    if not os.path.isfile(local):
        return "missing", 0
    size = len(proof_body(local).encode("utf-8", "replace"))
    if size <= MIN_PROOF_BYTES:
        return "tiny", size
    return "ok", size


def item_tokens(item, limit: int = ITEM_TOKEN_SAMPLE):
    seen, out = set(), []
    for w in re.findall(r"[A-Za-z][A-Za-z0-9_]{3,}", str(item or "")):
        lw = w.lower()
        if lw in _STOP or lw in seen:
            continue
        seen.add(lw)
        out.append(lw)
        if len(out) >= limit:
            break
    return out


def token_overlap(item, artifact_text):
    toks = item_tokens(item)
    if not toks:
        return 1, 1  # nothing to anchor against -> do not fail on it
    body = str(artifact_text or "").lower()
    return sum(1 for t in toks if t in body), len(toks)


def check_completion(item, proof_path, score) -> list[str]:
    """Pure predicate. Returns list of violations (empty == law-compliant)."""
    bad = []
    verdict, size = classify_proof_path(proof_path)
    if verdict != "ok":
        bad.append(f"L1-3 proof artifact {verdict} ({proof_path!r}, {size}B)")
    if score is None:
        bad.append("L4 quality_score is NULL (NULL must not evade the score floor)")
    else:
        try:
            numeric_score = float(score)
            if not math.isfinite(numeric_score):
                bad.append(f"L4 quality_score {score!r} must be finite")
            elif not 0 <= numeric_score <= 10:
                bad.append(f"L4 quality_score {score!r} is outside the documented 0-10 range")
            elif numeric_score < MIN_QUALITY_SCORE:
                bad.append(f"L4 quality_score {score} < {MIN_QUALITY_SCORE}")
        except (TypeError, ValueError):
            bad.append(f"L4 quality_score {score!r} is not numeric")
    if verdict == "ok":
        text = proof_body(proof_path)
        hit, total = token_overlap(item, text)
        if hit == 0:
            bad.append(f"L5 off-topic: 0/{total} task tokens found in artifact")
    return bad


def write_proof_first(task_id, raw_output, item: Optional[str] = None,
                       dest: Optional[str] = None, root: str = ".") -> str:
    """Step 1: raw output lands on disk BEFORE any state write, is
    flushed+fsynced, and is read back. Returns the absolute path."""
    path = Path(dest) if dest else (Path(root) / "proofs" / str(task_id) / "output.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    header = (f"# Task {task_id} proof artifact\n"
              f"written_by: proofgate.write_proof_first\n"
              f"written_at: {stamp}\n")
    if item:
        header += f"item: {str(item)[:400]}\n"
    body = header + "\n" + BODY_MARKER + "\n" + str(raw_output or "")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
        fh.flush()
        os.fsync(fh.fileno())
    verdict, size = classify_proof_path(str(path))  # readback, body-only size
    if verdict != "ok":
        raise ProofRefused(
            f"artifact failed readback: {verdict} ({size}B of real output, "
            f"floor is >{MIN_PROOF_BYTES}B). A header is not evidence.")
    return str(path)


def complete_with_proof(task_id, item, raw_output, score, *,
                         on_pass: Optional[Callable[[str], None]] = None,
                         dest: Optional[str] = None, root: str = ".") -> str:
    """Artifact FIRST, law check, THEN caller's state flip via on_pass.
    Raises ProofRefused otherwise. Returns the proof path on success.

    on_pass(proof_path) is your own "flip the row / close the ticket /
    mark the task done" callback -- proofgate does not know your storage.
    """
    proof_path = write_proof_first(task_id, raw_output, item=item, dest=dest, root=root)
    violations = check_completion(item, proof_path, score)
    if violations:
        raise ProofRefused(
            f"REFUSED completion of {task_id!r} -- artifact stays on disk at "
            f"{proof_path}, state NOT flipped. Violations: " + "; ".join(violations))
    if on_pass is not None:
        on_pass(proof_path)
    return proof_path
