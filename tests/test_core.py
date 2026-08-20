import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from proofgate import ProofRefused, complete_with_proof, check_completion, classify_proof_path


def test_stub_output_is_refused(tmp_path):
    try:
        complete_with_proof("t1", "deploy the api gateway", "exit=0", score=9, root=str(tmp_path))
        assert False, "a 6-byte stub must be refused"
    except ProofRefused as exc:
        assert "tiny" in str(exc)  # refused at the write-stage size floor, before scoring


def test_off_topic_proof_is_refused(tmp_path):
    real_output = ("unrelated wallpaper changer finished successfully with zero errors, "
                   "took 4 seconds, wrote 3 files, and exited with status code 0 overall")
    try:
        complete_with_proof("t2", "deploy the api gateway to production", real_output,
                             score=9, root=str(tmp_path))
        assert False, "proof with zero overlapping task tokens must be refused"
    except ProofRefused as exc:
        assert "L5" in str(exc)


def test_low_score_is_refused(tmp_path):
    real_output = ("ran deploy for api gateway: 200 OK, rollout complete, 12 pods healthy, "
                   "latency p50 40ms, no errors in the rollout log")
    try:
        complete_with_proof("t3", "deploy the api gateway", real_output, score=4, root=str(tmp_path))
        assert False, "score below floor must be refused"
    except ProofRefused as exc:
        assert "L4" in str(exc)


def test_null_score_is_refused(tmp_path):
    real_output = ("ran deploy for api gateway: 200 OK, rollout complete, 12 pods healthy, "
                   "latency p50 40ms, no errors in the rollout log")
    try:
        complete_with_proof("t4", "deploy the api gateway", real_output, score=None, root=str(tmp_path))
        assert False, "NULL score must not evade the floor"
    except ProofRefused as exc:
        assert "L4" in str(exc)


def test_real_proof_passes(tmp_path):
    real_output = ("ran deploy for api gateway: 200 OK, rollout complete, 12 pods healthy, "
                   "latency p50 40ms, no errors in the rollout log, verified against staging")
    flipped = {}
    path = complete_with_proof(
        "t5", "deploy the api gateway", real_output, score=9,
        on_pass=lambda p: flipped.setdefault("path", p), root=str(tmp_path),
    )
    assert flipped["path"] == path
    verdict, size = classify_proof_path(path)
    assert verdict == "ok"
    assert size > 100


def test_prose_path_is_not_a_path(tmp_path):
    bad = check_completion("deploy the api gateway", "I deployed it and it works great.", 9)
    assert any("not_a_path" in v for v in bad)
