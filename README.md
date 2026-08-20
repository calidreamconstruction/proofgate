# proofgate

A write-side proof gate for AI agents. An agent that can mark its own task
"done" can also lie about it — proofgate is the check that sits between
"the agent says it's done" and "the state actually changes."

## Why

Autonomous coding/ops agents routinely flip a task to `completed` with:
- a 9-byte stub ("exit=0", "done", "ok") instead of real command output
- a proof file that references a *different* task than the one just run
- no evidence artifact at all, just prose claiming success

We hit this in production: a task tracker where several completions were
later found to be fabricated — the referenced proof either didn't exist, was
a stub, or was off-topic. The read-side auditor that used to catch this after
the fact was retired. proofgate closes the hole on the **write side** instead:
the artifact has to exist, pass every check, and only then is the caller
allowed to flip state.

## The five checks (anchor laws)

A completion is refused unless **all** of these hold:

1. **L1** — the proof value is a real filesystem path, not prose or a URL
2. **L2** — the file exists on disk after the write
3. **L3** — the artifact body is more than 100 bytes (kills stub output)
4. **L4** — a quality score is present and non-null, and meets your floor
5. **L5** — at least one significant token from the task description shows
   up in the artifact body (catches proof copy-pasted from an unrelated task)

## Install

```bash
pip install -e .
```

## Use as a library

```python
from proofgate import complete_with_proof, ProofRefused

def flip_my_own_state(proof_path):
    my_db.mark_done(task_id, proof_path)

try:
    path = complete_with_proof(
        task_id="deploy-42",
        item="deploy the api gateway to production",
        raw_output=command_stdout,   # the real output, not a summary
        score=9,                     # your own honest 0-10 self-assessment
        on_pass=flip_my_own_state,
    )
except ProofRefused as exc:
    # state was NOT flipped; the artifact stays on disk for inspection
    raise
```

## Use as a CLI

```bash
some_command 2>&1 | proofgate --id deploy-42 --score 9 --item "deploy the api gateway"
```

Exit `0` = proof accepted. Exit `2` = refused, reason on stderr, nothing was
flipped.

## What this is not

This is not a general "is the code correct" checker — it doesn't run your
tests or read your diff. It's a narrow, cheap gate against the specific
failure mode of an agent *claiming* completion without evidence. Pair it
with real verification (tests, review, health checks); proofgate just makes
sure that verification's output can't be skipped or faked at the reporting
step.

## Status

v0.1 — the proof gate is extracted and tested. A companion "doctor" (a suite
of environment/health checks an agent can run before claiming a task is
done) is planned but not included in this release; see issues.

## License

MIT
