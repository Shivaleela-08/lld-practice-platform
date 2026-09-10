"""
DeterministicEvaluator

Cheap, explainable, always-runs-first checks that don't need judgement:
- did the learner cover the problem's stated requirements (keyword/coverage check)?
- is there evidence of class/responsibility thinking (structural markers)?
- is there any evidence of edge-case or testing awareness?

This mirrors the helping guide's split: "required fields / structure",
"known business rules", "state transitions" are deterministic; "quality of
responsibilities" and "design trade-offs" are judgement calls left to the
AIEvaluator. Keeping this evaluator LLM-free means the practice loop always
returns *some* fast, reliable feedback even if the AI evaluator is slow,
rate-limited, or down.
"""

import re
from typing import List

from domain.models import (
    DimensionScore,
    EvaluationResult,
    EvaluatorKind,
    Problem,
    Submission,
)
from evaluators.base import Evaluator

STRUCTURE_MARKERS = ["class ", "interface ", "def ", "responsibility", "responsibilities"]
EDGE_CASE_MARKERS = ["edge case", "failure", "error", "concurrent", "test", "invalid", "null"]


class DeterministicEvaluator(Evaluator):
    def evaluate(self, problem: Problem, submission: Submission) -> EvaluationResult:
        text = submission.content.lower()
        scores: List[DimensionScore] = []

        scores.append(self._score_requirement_coverage(problem, text))
        scores.append(self._score_structure(text))
        scores.append(self._score_edge_cases(text))

        return EvaluationResult.create(
            submission_id=submission.id,
            kind=EvaluatorKind.DETERMINISTIC,
            scores=scores,
            confidence=1.0,  # deterministic checks are exact, not opinions
        )

    def _score_requirement_coverage(self, problem: Problem, text: str) -> DimensionScore:
        hit, total = 0, len(problem.requirements) or 1
        missing = []
        for req in problem.requirements:
            # cheap coverage heuristic: any distinctive word from the requirement appears
            words = [w for w in re.findall(r"[a-zA-Z]{4,}", req.lower())]
            if any(w in text for w in words):
                hit += 1
            else:
                missing.append(req)
        ratio = hit / total
        score = max(1, min(5, round(1 + ratio * 4)))
        return DimensionScore(
            criterion="requirement_understanding",
            score=score,
            evidence=f"{hit}/{total} stated requirements referenced in the submission.",
            concern=("Not addressed: " + "; ".join(missing[:3])) if missing else None,
            suggestion="Explicitly restate each requirement and how your design satisfies it."
            if missing else None,
        )

    def _score_structure(self, text: str) -> DimensionScore:
        hits = [m for m in STRUCTURE_MARKERS if m in text]
        score = max(1, min(5, 1 + len(hits)))
        return DimensionScore(
            criterion="class_responsibilities",
            score=score,
            evidence=f"Found structural markers: {hits or 'none'}.",
            concern=None if hits else "No explicit classes/interfaces/responsibilities found.",
            suggestion=None if hits else "Name your classes explicitly and state what each one owns.",
        )

    def _score_edge_cases(self, text: str) -> DimensionScore:
        hits = [m for m in EDGE_CASE_MARKERS if m in text]
        score = max(1, min(5, 1 + len(hits)))
        return DimensionScore(
            criterion="edge_cases_testability",
            score=score,
            evidence=f"Found edge-case/testing language: {hits or 'none'}.",
            concern=None if hits else "No mention of edge cases, failures, or tests.",
            suggestion=None if hits else "Add a short section on what could go wrong and how it's handled.",
        )
