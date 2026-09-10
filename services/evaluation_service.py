"""
EvaluationService

Owns the practice loop end to end and answers the assignment's practical
question directly: "what happens if evaluation takes time or fails?"

- The Submission is saved and the Attempt moved to SUBMITTED *before* any
  evaluator runs, so a slow/failing evaluator can never lose the learner's
  work.
- Evaluation then runs on a background thread so POST /submissions returns
  immediately with status EVALUATING; the frontend polls GET /attempts/:id
  until it sees COMPLETED or FAILED. This is the simplest thing that could
  work for a 2-day MVP - a real deployment would swap the thread for a
  queue/worker (see DESIGN_NOTE.md) without changing this class's public
  interface.
- Only one evaluation may be in flight per Attempt at a time (guarded by
  the state machine itself - EVALUATING has no legal transition back into
  EVALUATING), which is what prevents duplicate/racing evaluation if the
  learner double-clicks submit or retries.
- On FAILED, `retry()` re-enters EVALUATING and re-runs the full evaluator
  pipeline against the *same* stored Submission - nothing is re-entered by
  the learner.
"""

import threading
from typing import List, Optional

from db import AttemptRepository, EvaluationResultRepository, ProblemRepository, SubmissionRepository
from domain.models import (
    Attempt,
    AttemptStatus,
    DimensionScore,
    EvaluationResult,
    EvaluatorKind,
    Feedback,
    Submission,
    SubmissionFormat,
)
from evaluators.factory import EvaluatorFactory


class EvaluationService:
    def __init__(
        self,
        problems: ProblemRepository,
        attempts: AttemptRepository,
        submissions: SubmissionRepository,
        results: EvaluationResultRepository,
    ):
        self.problems = problems
        self.attempts = attempts
        self.submissions = submissions
        self.results = results

    # -- Practice loop entry points -----------------------------------

    def start_attempt(self, problem_id: str, learner_id: str) -> Attempt:
        if not self.problems.get(problem_id):
            raise ValueError(f"Unknown problem_id: {problem_id}")
        attempt = Attempt.start(problem_id, learner_id)
        self.attempts.save(attempt)
        return attempt

    def submit(self, attempt_id: str, content: str, fmt: str) -> Attempt:
        attempt = self._require_attempt(attempt_id)
        if not content or not content.strip():
            raise ValueError("Submission content cannot be empty.")

        submission = Submission.create(attempt_id, content, SubmissionFormat(fmt))
        self.submissions.save(submission)  # persisted BEFORE evaluation starts

        attempt.submission_id = submission.id
        attempt.transition_to(AttemptStatus.SUBMITTED)
        self.attempts.save(attempt)

        self._run_evaluation_async(attempt.id, submission.id)
        return attempt

    def retry(self, attempt_id: str) -> Attempt:
        attempt = self._require_attempt(attempt_id)
        if attempt.status != AttemptStatus.FAILED:
            raise ValueError("Can only retry an attempt that FAILED.")
        if not attempt.submission_id:
            raise ValueError("No submission to retry.")
        self._run_evaluation_async(attempt.id, attempt.submission_id)
        return attempt

    def get_feedback(self, submission_id: str) -> Optional[Feedback]:
        results = self.results.list_for_submission(submission_id)
        if not results:
            return None
        return self._aggregate(submission_id, results)

    # -- Internal ------------------------------------------------------

    def _run_evaluation_async(self, attempt_id: str, submission_id: str) -> None:
        attempt = self._require_attempt(attempt_id)
        attempt.transition_to(AttemptStatus.EVALUATING)
        self.attempts.save(attempt)
        thread = threading.Thread(
            target=self._run_evaluation_sync, args=(attempt_id, submission_id), daemon=True
        )
        thread.start()

    def _run_evaluation_sync(self, attempt_id: str, submission_id: str) -> None:
        attempt = self._require_attempt(attempt_id)
        problem = self.problems.get(attempt.problem_id)
        submission = self.submissions.get(submission_id)
        pipeline = EvaluatorFactory.build_pipeline()

        had_failure = False
        first_error = None
        for evaluator in pipeline:
            try:
                result = evaluator.evaluate(problem, submission)
                self.results.save(result)
            except Exception as exc:  # noqa: BLE001 - deliberately broad: any evaluator may fail
                had_failure = had_failure or isinstance(evaluator, type(pipeline[-1]))
                first_error = first_error or str(exc)
                # Deterministic evaluator failing is unexpected (it's pure logic);
                # AI evaluator failing (rate limit, no key, bad JSON) is expected
                # and handled gracefully: we keep whatever results we already have.
                continue

        existing = self.results.list_for_submission(submission_id)
        if not existing:
            attempt.failure_reason = first_error or "All evaluators failed."
            attempt.transition_to(AttemptStatus.FAILED)
        else:
            attempt.failure_reason = None
            attempt.transition_to(AttemptStatus.COMPLETED)
        self.attempts.save(attempt)

    def _aggregate(self, submission_id: str, results: List[EvaluationResult]) -> Feedback:
        # Merge dimension scores across evaluators. Where both evaluators
        # scored the same criterion, weight by confidence; AI evaluator is
        # the tie-breaker for judgement-heavy dimensions since it's the only
        # one that scores them.
        by_criterion = {}
        for r in results:
            for d in r.dimension_scores:
                by_criterion.setdefault(d.criterion, []).append((d, r.confidence))

        merged: List[DimensionScore] = []
        for criterion, scored in by_criterion.items():
            total_weight = sum(w for _, w in scored) or 1
            avg_score = round(sum(d.score * w for d, w in scored) / total_weight)
            # prefer the highest-confidence evaluator's qualitative text
            best = max(scored, key=lambda t: t[1])[0]
            merged.append(DimensionScore(
                criterion=criterion, score=avg_score,
                evidence=best.evidence, concern=best.concern, suggestion=best.suggestion,
            ))

        overall = round(sum(d.score for d in merged) / (len(merged) or 1), 2)
        strengths = [f"{d.criterion.replace('_', ' ')}: {d.evidence}" for d in merged if d.score >= 4]
        improvements = [f"{d.criterion.replace('_', ' ')}: {d.suggestion}" for d in merged if d.suggestion]

        summary = (
            f"Overall {overall}/5 across {len(merged)} rubric dimensions. "
            f"{'Strong requirement coverage and structure.' if overall >= 4 else 'Some rubric dimensions need more evidence in the design.'}"
        )

        return Feedback(
            submission_id=submission_id, overall_score=overall, summary=summary,
            strengths=strengths, improvements=improvements, dimension_scores=merged,
        )

    def _require_attempt(self, attempt_id: str) -> Attempt:
        attempt = self.attempts.get(attempt_id)
        if not attempt:
            raise ValueError(f"Unknown attempt_id: {attempt_id}")
        return attempt
