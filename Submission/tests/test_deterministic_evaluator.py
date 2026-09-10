import unittest

from domain.models import Problem, Submission, SubmissionFormat
from evaluators.deterministic import DeterministicEvaluator


class TestDeterministicEvaluator(unittest.TestCase):
    def setUp(self):
        self.evaluator = DeterministicEvaluator()
        self.problem = Problem(
            id="p1", title="Vending Machine", difficulty="Easy",
            summary="...",
            requirements=["Track inventory per item slot", "Accept incremental payment"],
        )

    def test_strong_submission_scores_well(self):
        content = (
            "class VendingMachine: tracks inventory per item slot and current balance. "
            "Accepts incremental payment via insertCoin(). Handles edge cases like "
            "insufficient payment and out-of-stock items with tests for each."
        )
        sub = Submission.create("att1", content, SubmissionFormat.TEXT_DESIGN)
        result = self.evaluator.evaluate(self.problem, sub)
        scores = {d.criterion: d.score for d in result.dimension_scores}
        self.assertGreaterEqual(scores["requirement_understanding"], 4)
        self.assertGreaterEqual(scores["class_responsibilities"], 2)
        self.assertGreaterEqual(scores["edge_cases_testability"], 2)

    def test_empty_ish_submission_scores_low_with_concerns(self):
        content = "I would build a vending machine."
        sub = Submission.create("att1", content, SubmissionFormat.TEXT_DESIGN)
        result = self.evaluator.evaluate(self.problem, sub)
        scores = {d.criterion: d for d in result.dimension_scores}
        self.assertLessEqual(scores["requirement_understanding"].score, 2)
        self.assertIsNotNone(scores["class_responsibilities"].concern)

    def test_confidence_is_always_certain(self):
        sub = Submission.create("att1", "class X {}", SubmissionFormat.CODE)
        result = self.evaluator.evaluate(self.problem, sub)
        self.assertEqual(result.confidence, 1.0)


if __name__ == "__main__":
    unittest.main()
