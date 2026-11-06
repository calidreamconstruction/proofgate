"""Regression tests for non-finite and out-of-range completion scores."""
import tempfile
import unittest

from proofgate.core import check_completion, write_proof_first


class QualityScoreLimitsTests(unittest.TestCase):
    def test_finite_documented_scores_only(self):
        with tempfile.TemporaryDirectory() as root:
            path = write_proof_first(
                "score-limits",
                "Validated score limits using real proofgate completion checks. " * 5,
                item="validate score limits",
                root=root,
            )

            for score in (7, 8.5, 10, "9"):
                with self.subTest(score=score):
                    self.assertEqual(check_completion("validate score limits", path, score), [])

            for score in (float("nan"), float("inf"), -float("inf"), "NaN", "Infinity"):
                with self.subTest(score=score):
                    violations = check_completion("validate score limits", path, score)
                    self.assertTrue(any("must be finite" in line for line in violations), violations)

            for score in (-1, 10.01, 100):
                with self.subTest(score=score):
                    violations = check_completion("validate score limits", path, score)
                    self.assertTrue(any("outside the documented 0-10 range" in line for line in violations), violations)

            violations = check_completion("validate score limits", path, 6.99)
            self.assertTrue(any("quality_score" in line for line in violations), violations)

            violations = check_completion("validate score limits", path, "not-a-number")
            self.assertTrue(any("not numeric" in line for line in violations), violations)


if __name__ == "__main__":
    unittest.main()
