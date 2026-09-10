import unittest

from domain.models import Attempt, AttemptStatus


class TestAttemptStateMachine(unittest.TestCase):
    def test_happy_path(self):
        a = Attempt.start("parking-lot", "learner-1")
        self.assertEqual(a.status, AttemptStatus.IN_PROGRESS)
        a.transition_to(AttemptStatus.SUBMITTED)
        a.transition_to(AttemptStatus.EVALUATING)
        a.transition_to(AttemptStatus.COMPLETED)
        self.assertEqual(a.status, AttemptStatus.COMPLETED)

    def test_failed_then_retry(self):
        a = Attempt.start("parking-lot", "learner-1")
        a.transition_to(AttemptStatus.SUBMITTED)
        a.transition_to(AttemptStatus.EVALUATING)
        a.transition_to(AttemptStatus.FAILED)
        a.transition_to(AttemptStatus.EVALUATING)  # retry
        a.transition_to(AttemptStatus.COMPLETED)
        self.assertEqual(a.status, AttemptStatus.COMPLETED)

    def test_illegal_transition_raises(self):
        a = Attempt.start("parking-lot", "learner-1")
        with self.assertRaises(ValueError):
            a.transition_to(AttemptStatus.EVALUATING)  # can't skip SUBMITTED

    def test_completed_is_terminal(self):
        a = Attempt.start("parking-lot", "learner-1")
        a.transition_to(AttemptStatus.SUBMITTED)
        a.transition_to(AttemptStatus.EVALUATING)
        a.transition_to(AttemptStatus.COMPLETED)
        with self.assertRaises(ValueError):
            a.transition_to(AttemptStatus.EVALUATING)

    def test_no_double_evaluation(self):
        # EVALUATING has no self-loop, so a second concurrent evaluation
        # attempt cannot be started while one is in flight.
        a = Attempt.start("parking-lot", "learner-1")
        a.transition_to(AttemptStatus.SUBMITTED)
        a.transition_to(AttemptStatus.EVALUATING)
        with self.assertRaises(ValueError):
            a.transition_to(AttemptStatus.EVALUATING)


if __name__ == "__main__":
    unittest.main()
