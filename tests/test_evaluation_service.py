import os
import tempfile
import time
import unittest
from unittest.mock import patch

from db import AttemptRepository, Database, EvaluationResultRepository, ProblemRepository, SubmissionRepository
from domain.models import AttemptStatus, DimensionScore, EvaluationResult, EvaluatorKind, Problem
from evaluators.base import Evaluator
from services.evaluation_service import EvaluationService


class AlwaysSucceedsEvaluator(Evaluator):
    """Test double standing in for the deterministic evaluator."""
    def evaluate(self, problem, submission):
        return EvaluationResult.create(
            submission_id=submission.id, kind=EvaluatorKind.DETERMINISTIC,
            scores=[DimensionScore("requirement_understanding", 4, "ok", None, None)],
            confidence=1.0,
        )


class AlwaysFailsEvaluator(Evaluator):
    """Test double standing in for a down/misconfigured AI evaluator."""
    def evaluate(self, problem, submission):
        raise RuntimeError("simulated AI outage")


def wait_for(predicate, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


class TestEvaluationService(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db = Database(os.path.join(self.tmpdir, "test.db"))
        self.problems = ProblemRepository(self.db)
        self.attempts = AttemptRepository(self.db)
        self.submissions = SubmissionRepository(self.db)
        self.results = EvaluationResultRepository(self.db)
        self.service = EvaluationService(self.problems, self.attempts, self.submissions, self.results)
        self.problems.upsert(Problem(
            id="p1", title="Test Problem", difficulty="Easy", summary="s",
            requirements=["Do the thing"],
        ))

    @patch("services.evaluation_service.EvaluatorFactory.build_pipeline")
    def test_happy_path_reaches_completed(self, mock_pipeline):
        mock_pipeline.return_value = [AlwaysSucceedsEvaluator()]
        attempt = self.service.start_attempt("p1", "learner-1")
        self.service.submit(attempt.id, "some design content", "TEXT_DESIGN")

        self.assertTrue(wait_for(
            lambda: self.attempts.get(attempt.id).status in (AttemptStatus.COMPLETED, AttemptStatus.FAILED)
        ))
        final = self.attempts.get(attempt.id)
        self.assertEqual(final.status, AttemptStatus.COMPLETED)
        feedback = self.service.get_feedback(final.submission_id)
        self.assertIsNotNone(feedback)
        self.assertGreater(feedback.overall_score, 0)

    @patch("services.evaluation_service.EvaluatorFactory.build_pipeline")
    def test_partial_evaluator_failure_still_completes(self, mock_pipeline):
        # deterministic succeeds, AI fails -> should still COMPLETE with
        # whatever results exist (graceful degradation), not FAIL outright.
        mock_pipeline.return_value = [AlwaysSucceedsEvaluator(), AlwaysFailsEvaluator()]
        attempt = self.service.start_attempt("p1", "learner-1")
        self.service.submit(attempt.id, "some design content", "TEXT_DESIGN")

        wait_for(lambda: self.attempts.get(attempt.id).status in (AttemptStatus.COMPLETED, AttemptStatus.FAILED))
        self.assertEqual(self.attempts.get(attempt.id).status, AttemptStatus.COMPLETED)

    @patch("services.evaluation_service.EvaluatorFactory.build_pipeline")
    def test_total_failure_then_retry_recovers(self, mock_pipeline):
        mock_pipeline.return_value = [AlwaysFailsEvaluator()]
        attempt = self.service.start_attempt("p1", "learner-1")
        self.service.submit(attempt.id, "some design content", "TEXT_DESIGN")
        wait_for(lambda: self.attempts.get(attempt.id).status in (AttemptStatus.COMPLETED, AttemptStatus.FAILED))
        self.assertEqual(self.attempts.get(attempt.id).status, AttemptStatus.FAILED)
        self.assertIsNotNone(self.attempts.get(attempt.id).failure_reason)

        # Submission must have survived the failure - retry re-uses it.
        mock_pipeline.return_value = [AlwaysSucceedsEvaluator()]
        self.service.retry(attempt.id)
        wait_for(lambda: self.attempts.get(attempt.id).status in (AttemptStatus.COMPLETED, AttemptStatus.FAILED))
        self.assertEqual(self.attempts.get(attempt.id).status, AttemptStatus.COMPLETED)

    def test_empty_submission_rejected(self):
        attempt = self.service.start_attempt("p1", "learner-1")
        with self.assertRaises(ValueError):
            self.service.submit(attempt.id, "   ", "TEXT_DESIGN")

    def test_unknown_problem_rejected(self):
        with self.assertRaises(ValueError):
            self.service.start_attempt("does-not-exist", "learner-1")

    def test_unknown_attempt_rejected(self):
        with self.assertRaises(ValueError):
            self.service.submit("att_doesnotexist", "content", "TEXT_DESIGN")


if __name__ == "__main__":
    unittest.main()
