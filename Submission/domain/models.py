"""
Domain model for the LLD Practice Platform.

Design intent
--------------
Each class owns exactly one responsibility so the practice loop
(Choose problem -> Design -> Submit -> Get feedback -> Review -> Retry)
stays easy to reason about and easy to extend.

    Problem     -> what the learner is asked to design (read-only content)
    Attempt     -> one learner's run at a Problem; owns lifecycle state
    Submission  -> one piece of submitted work inside an Attempt (polymorphic
                   on `format`, so a future diagram/code submission doesn't
                   require changing Attempt or the evaluation pipeline)
    Rubric      -> the fixed set of dimensions every evaluator scores against
    EvaluationResult -> the output of ONE evaluator run (deterministic or AI)
    Feedback    -> the learner-facing aggregation of every EvaluationResult
                   for a submission

State machine
-------------
AttemptStatus:
    IN_PROGRESS -> SUBMITTED -> EVALUATING -> COMPLETED
                                            -> FAILED -> EVALUATING (retry)

The submission is always persisted *before* evaluation starts, so a slow or
failing evaluator can never lose the learner's work (see EvaluationService).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def now_ts() -> float:
    return time.time()


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AttemptStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    EVALUATING = "EVALUATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# Legal transitions for the Attempt state machine. Kept as data (not
# scattered if/else) so EvaluationService can validate every transition in
# one place and new states are a one-line change.
ALLOWED_TRANSITIONS = {
    AttemptStatus.IN_PROGRESS: {AttemptStatus.SUBMITTED},
    AttemptStatus.SUBMITTED: {AttemptStatus.EVALUATING},
    AttemptStatus.EVALUATING: {AttemptStatus.COMPLETED, AttemptStatus.FAILED},
    AttemptStatus.FAILED: {AttemptStatus.EVALUATING},  # retry
    AttemptStatus.COMPLETED: set(),  # terminal
}


class SubmissionFormat(str, Enum):
    TEXT_DESIGN = "TEXT_DESIGN"   # prose design write-up (requirements, classes, reasoning)
    CODE = "CODE"                  # source code
    DIAGRAM_TEXT = "DIAGRAM_TEXT"  # textual UML (e.g. PlantUML/Mermaid) - future-ready


class EvaluatorKind(str, Enum):
    DETERMINISTIC = "DETERMINISTIC"
    AI = "AI"


# ---------------------------------------------------------------------------
# Problem
# ---------------------------------------------------------------------------

@dataclass
class Problem:
    """A practice problem. Immutable content owned by the platform, not the learner."""
    id: str
    title: str
    difficulty: str
    summary: str
    requirements: List[str]
    hints: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "difficulty": self.difficulty,
            "summary": self.summary,
            "requirements": self.requirements,
            "hints": self.hints,
            "tags": self.tags,
        }


# ---------------------------------------------------------------------------
# Rubric
# ---------------------------------------------------------------------------

# Fixed, shared rubric. Both evaluator types score against a subset of these
# dimensions so learner-facing feedback always reads consistently regardless
# of which evaluator produced it.
RUBRIC_DIMENSIONS = [
    "requirement_understanding",
    "class_responsibilities",
    "coupling_cohesion",
    "encapsulation_interfaces",
    "abstraction_patterns",
    "extensibility",
    "edge_cases_testability",
    "explanation_quality",
]

DETERMINISTIC_DIMENSIONS = {
    # Dimensions cheap/objective enough to check without an LLM.
    "requirement_understanding",
    "class_responsibilities",
    "edge_cases_testability",
}

AI_DIMENSIONS = [d for d in RUBRIC_DIMENSIONS if d not in DETERMINISTIC_DIMENSIONS] + [
    # AI re-checks these two qualitatively too, deterministic only catches
    # surface-level presence/absence.
    "class_responsibilities",
    "requirement_understanding",
]


@dataclass
class DimensionScore:
    """One rubric dimension, scored by one evaluator."""
    criterion: str
    score: int              # 1-5
    evidence: str           # quote/paraphrase of what in the submission supports the score
    concern: Optional[str]  # what's weak, if anything
    suggestion: Optional[str]

    def to_dict(self) -> dict:
        return {
            "criterion": self.criterion,
            "score": self.score,
            "evidence": self.evidence,
            "concern": self.concern,
            "suggestion": self.suggestion,
        }


# ---------------------------------------------------------------------------
# Submission
# ---------------------------------------------------------------------------

@dataclass
class Submission:
    """One piece of submitted work for an Attempt."""
    id: str
    attempt_id: str
    content: str
    format: SubmissionFormat
    created_at: float

    @staticmethod
    def create(attempt_id: str, content: str, fmt: SubmissionFormat) -> "Submission":
        return Submission(
            id=new_id("sub"),
            attempt_id=attempt_id,
            content=content,
            format=fmt,
            created_at=now_ts(),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "attempt_id": self.attempt_id,
            "content": self.content,
            "format": self.format.value,
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# Evaluation result + Feedback
# ---------------------------------------------------------------------------

@dataclass
class EvaluationResult:
    """Output of ONE evaluator run against ONE submission."""
    id: str
    submission_id: str
    evaluator_kind: EvaluatorKind
    dimension_scores: List[DimensionScore]
    confidence: float          # 0-1, how much weight to give this evaluator's opinion
    error: Optional[str] = None

    @staticmethod
    def create(submission_id: str, kind: EvaluatorKind,
               scores: List[DimensionScore], confidence: float,
               error: Optional[str] = None) -> "EvaluationResult":
        return EvaluationResult(
            id=new_id("eval"),
            submission_id=submission_id,
            evaluator_kind=kind,
            dimension_scores=scores,
            confidence=confidence,
            error=error,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "submission_id": self.submission_id,
            "evaluator_kind": self.evaluator_kind.value,
            "dimension_scores": [d.to_dict() for d in self.dimension_scores],
            "confidence": self.confidence,
            "error": self.error,
        }


@dataclass
class Feedback:
    """Learner-facing aggregation of every EvaluationResult for a submission."""
    submission_id: str
    overall_score: float
    summary: str
    strengths: List[str]
    improvements: List[str]
    dimension_scores: List[DimensionScore]

    def to_dict(self) -> dict:
        return {
            "submission_id": self.submission_id,
            "overall_score": self.overall_score,
            "summary": self.summary,
            "strengths": self.strengths,
            "improvements": self.improvements,
            "dimension_scores": [d.to_dict() for d in self.dimension_scores],
        }


# ---------------------------------------------------------------------------
# Attempt (owns lifecycle state)
# ---------------------------------------------------------------------------

@dataclass
class Attempt:
    """One learner's run at a Problem. Owns the state machine."""
    id: str
    problem_id: str
    learner_id: str
    status: AttemptStatus
    created_at: float
    updated_at: float
    submission_id: Optional[str] = None
    failure_reason: Optional[str] = None

    @staticmethod
    def start(problem_id: str, learner_id: str) -> "Attempt":
        ts = now_ts()
        return Attempt(
            id=new_id("att"),
            problem_id=problem_id,
            learner_id=learner_id,
            status=AttemptStatus.IN_PROGRESS,
            created_at=ts,
            updated_at=ts,
        )

    def transition_to(self, new_status: AttemptStatus) -> None:
        """The single place transitions are validated. Raises on an illegal move."""
        allowed = ALLOWED_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Illegal transition: {self.status.value} -> {new_status.value}"
            )
        self.status = new_status
        self.updated_at = now_ts()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "problem_id": self.problem_id,
            "learner_id": self.learner_id,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "submission_id": self.submission_id,
            "failure_reason": self.failure_reason,
        }
