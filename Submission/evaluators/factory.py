"""
EvaluatorFactory

Single place that knows which Evaluator implementations exist and in what
order they run. Adding a new evaluator (e.g. RuleBasedEvaluator,
HumanReviewEvaluator) is a one-line addition here; nothing else in the
system needs to change (see evaluators/base.py for why).
"""

from typing import List

from evaluators.ai_evaluator import AIEvaluator
from evaluators.base import Evaluator
from evaluators.deterministic import DeterministicEvaluator


class EvaluatorFactory:
    @staticmethod
    def build_pipeline() -> List[Evaluator]:
        return [
            DeterministicEvaluator(),  # always runs, fast, no external dependency
            AIEvaluator(),             # judgement-heavy dimensions, can fail/be slow
        ]
