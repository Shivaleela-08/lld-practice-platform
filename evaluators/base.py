"""
Evaluator interface.

This is the seam the assignment's "change test B" asks for: today we run a
DeterministicEvaluator and an AIEvaluator. Adding a RuleBasedEvaluator or a
HumanReviewEvaluator later means writing one new class that implements
`evaluate()` and registering it in EvaluatorFactory - nothing in
EvaluationService, the API layer, or the domain model has to change.
"""

from abc import ABC, abstractmethod

from domain.models import EvaluationResult, Problem, Submission


class Evaluator(ABC):
    """Strategy interface: score one Submission against one Problem."""

    @abstractmethod
    def evaluate(self, problem: Problem, submission: Submission) -> EvaluationResult:
        """Return an EvaluationResult. Must not raise for ordinary bad input -
        encode problems as a low score / concern instead. May raise for
        infrastructure failure (e.g. AI API unreachable); the caller
        (EvaluationService) is responsible for catching that and moving the
        Attempt to FAILED without losing the Submission."""
        raise NotImplementedError
