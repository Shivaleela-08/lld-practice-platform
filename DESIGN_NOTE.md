# Design Note

## MVP scope

Practice loop: **Choose problem -> Design -> Submit -> Get feedback -> Review
-> Retry**, for 5 seeded problems (Parking Lot, Elevator, Vending Machine,
Rate Limiter, Library). Single learner, no auth. A monolith: one Python
process, SQLite file, stdlib HTTP server, plain-JS frontend.

## User flow

1. Learner opens the Practice tab, sees problem cards with requirements.
2. Clicking "Start attempt" creates an `Attempt` and opens a workspace: a
   format picker (text design / code / text-UML) and a textarea.
3. Submitting creates a `Submission`, immediately returns `SUBMITTED`
   (then `EVALUATING`), and the frontend polls until the attempt reaches
   `COMPLETED` or `FAILED`.
4. Feedback renders as an overall score plus per-dimension scores, each
   with evidence, a concern (if any), and a suggestion (if any).
5. The History tab lists every past attempt with its status and, once
   complete, its feedback - so a learner can compare attempt 1 vs attempt 3
   on the same problem.

## Core classes and responsibilities

| Class | Owns |
|---|---|
| `Problem` | Immutable practice content: requirements, hints, difficulty |
| `Attempt` | Lifecycle state for one learner's run at a `Problem`; the only place transitions are validated (`transition_to`) |
| `Submission` | One piece of submitted work; polymorphic on `format` |
| `Evaluator` (interface) | `evaluate(problem, submission) -> EvaluationResult` |
| `DeterministicEvaluator` | Objective, LLM-free checks |
| `AIEvaluator` | Judgement-heavy checks via a fixed rubric + forced JSON output |
| `EvaluatorFactory` | The one place that knows which evaluators run, and in what order |
| `EvaluationResult` | One evaluator's scored output for one submission |
| `Feedback` | Learner-facing aggregation across all `EvaluationResult`s for a submission |
| `EvaluationService` | Orchestrates the loop end to end; owns the async/failure handling |
| `*Repository` (in `db.py`) | Persistence per aggregate, SQL isolated from domain/service code |

This maps directly onto the assignment's core-design ask: the important
domain behavior (what a learner needs, how evaluation is scored, what
happens on retry) lives in named classes with single responsibilities, not
scattered across route handlers.

## Answering the four design questions

**What does a learner need to provide for an attempt to be meaningful?**
Enough evidence to judge the eight rubric dimensions - not a specific
format. The `Submission.format` field is intentionally open (text design /
code / diagram-text) because what proves "requirement understanding" for
one learner might be prose and for another might be code; the MVP defaults
to text design as the lowest-effort format that still forces the learner to
name classes and responsibilities explicitly, per the helping guide's
"smallest format that gives enough evidence" principle.

**What makes feedback useful when more than one valid design exists?**
Two things: (1) every score is tied to *evidence quoted/paraphrased from
the submission*, never a bare number, so the learner can see what was
noticed rather than trust a black box; (2) the AI evaluator's prompt
explicitly tells it not to grade against one reference solution but to
judge soundness of reasoning and trade-offs (see `ai_evaluator.py`,
`SYSTEM_PROMPT`).

**Which parts should be deterministic vs. LLM-judged?**
`DeterministicEvaluator` handles requirement-coverage (keyword presence),
structural markers (are classes/interfaces/responsibilities named at all),
and edge-case language - things a regex can check honestly.
`AIEvaluator` handles coupling/cohesion, encapsulation quality, appropriate
abstraction, extensibility, and explanation quality - things that need
judgement. Both score against the *same* rubric vocabulary
(`RUBRIC_DIMENSIONS` in `domain/models.py`) so `EvaluationService`
can merge them into one `Feedback` without special-casing either source.

**How would the design accommodate another evaluation approach or
submission format later?**
- New evaluator (e.g. rule-based linter, human review queue): implement
  `Evaluator`, add one line to `EvaluatorFactory.build_pipeline()`. Nothing
  in `EvaluationService`, the API, or the frontend changes.
- New submission format (e.g. real UML diagrams): add an enum value to
  `SubmissionFormat`; evaluators that care about format can branch on it,
  evaluators that don't (most rubric dimensions) keep working unmodified,
  because `Submission.content` is always just a string the format
  describes rather than constrains.

**What happens if evaluation takes time or fails?**
The `Submission` is saved and the `Attempt` moved to `SUBMITTED` *before*
any evaluator runs - so a slow or crashing evaluator can never lose the
learner's work. Evaluation then runs on a background thread so the HTTP
response isn't blocked; the frontend polls `GET /attempts/:id`. If the AI
evaluator fails but the deterministic one succeeds, the attempt still
completes with the results that exist (graceful degradation - narrower
feedback, not no feedback). Only if *every* evaluator fails does the
attempt move to `FAILED`, with a stored reason and a `retry` endpoint that
re-runs the pipeline against the same stored submission. The state machine
itself (`EVALUATING` has no legal transition back into `EVALUATING`)
prevents two evaluations racing on the same attempt.

## Trade-offs and what a bigger version would change first

- **Background thread, not a queue.** Fine for one process and a handful of
  concurrent learners; the first thing to change at real scale is swapping
  `threading.Thread` in `EvaluationService._run_evaluation_async` for a
  task queue (e.g. RQ/Celery) - `EvaluationService`'s public methods
  (`submit`, `retry`, `get_feedback`) wouldn't need to change, only their
  internals.
- **SQLite, not Postgres.** One file, zero setup, fine for a prototype;
  each `*Repository` class is the seam to swap it later.
- **No auth.** Everything is scoped by a hardcoded `learner_id`; adding
  real accounts only touches the `learner_id` value's source, not the
  domain model.
- **Score aggregation is a simple confidence-weighted average**, not a
  tuned rubric-weighting scheme. Good enough to be explainable for an MVP;
  a real product would want per-dimension weights and probably a human
  audit of a sample of AI scores before trusting the number shown to
  learners.
