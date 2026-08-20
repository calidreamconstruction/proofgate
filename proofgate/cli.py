"""CLI: pipe a command's output through the gate.

    some_command 2>&1 | proofgate --id build-42 --score 8 --item "deploy step"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .core import ProofRefused, complete_with_proof


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--id", required=True, help="task identifier")
    ap.add_argument("--score", type=float, required=True,
                     help="honest 0-10 self-assessment; <7 is refused")
    ap.add_argument("--item", default="", help="task text, used as the topical anchor")
    ap.add_argument("--proof-file", default=None,
                     help="read raw output from this file instead of stdin")
    ap.add_argument("--dest", default=None, help="override artifact destination")
    ap.add_argument("--root", default=".", help="proof root when --dest is not given")
    a = ap.parse_args(argv)

    raw = Path(a.proof_file).read_text(encoding="utf-8", errors="replace") if a.proof_file else sys.stdin.read()

    try:
        path = complete_with_proof(a.id, a.item, raw, a.score, dest=a.dest, root=a.root)
    except ProofRefused as exc:
        sys.stderr.write(str(exc) + "\n")
        return 2

    print(f"PASSED {a.id} proof={path} score={a.score:g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
