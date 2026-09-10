# LLD Practice Platform

A small MVP that lets a learner pick an LLD problem (Parking Lot, Elevator,
Vending Machine, Rate Limiter, Library), submit a design, and get rubric-based
feedback - then see their attempt history and retry.

## Why this stack

Zero external dependencies: Python's standard library only
(`http.server`, `sqlite3`, `urllib`). No `pip install`, no Node/npm, no
virtual environment to activate. On Windows this also avoids the classic
`node_modules` path-length and venv-activation headaches - just run the
one command below.

## Run it

```bash
# 1. (optional) enable AI-judged feedback dimensions
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY=sk-ant-...
# on Windows (PowerShell), instead just run:
#   $env:ANTHROPIC_API_KEY="sk-ant-..."

# 2. start the server (only needs Python 3.9+, nothing else installed)
python server.py
```

Then open **http://localhost:8000** in a browser.

Without `ANTHROPIC_API_KEY` set, the platform still works end-to-end - it
just falls back to deterministic-only feedback (see `DESIGN_NOTE.md` for why
that fallback exists).

## Run the tests

```bash
python -m unittest discover -s tests -v
```

14 tests, no external services required (the AI evaluator is swapped for a
test double in the service-level tests, so the suite never needs a real API
key or network access).

## Project layout

```
domain/            Problem, Attempt, Submission, Rubric, EvaluationResult, Feedback
evaluators/         Evaluator interface + DeterministicEvaluator + AIEvaluator + factory
services/           EvaluationService - orchestrates the practice loop + state machine
db.py               SQLite persistence (one repository class per aggregate)
server.py           stdlib HTTP API + static file server
frontend/           plain HTML/CSS/JS single-page app (no build step)
data/problems.json  seed problems
tests/              unittest suite
```

## Key decisions (see DESIGN_NOTE.md for the full write-up)

- **Submission is persisted before evaluation runs.** A slow or failing
  evaluator can never lose the learner's work.
- **Two evaluators, one interface.** `DeterministicEvaluator` (fast, no LLM,
  checks requirement coverage / structural markers / edge-case language) and
  `AIEvaluator` (fixed rubric, forced JSON output, judges trade-offs and
  abstraction quality) both implement the same `Evaluator.evaluate()`
  contract, so a third evaluator (rule-based, human review) is a one-class
  addition.
- **Evaluation runs on a background thread**; the frontend polls
  `GET /attempts/:id`. Good enough for a 2-day MVP; the interface this hides
  behind (`EvaluationService`) is exactly what you'd keep if you swapped the
  thread for a real queue later.
- **Submission format is polymorphic** (`TEXT_DESIGN` / `CODE` /
  `DIAGRAM_TEXT`) so adding a diagram submission later doesn't require
  touching `Attempt` or the evaluators' interface.

## Limitations (deliberately out of scope for a 2-day prototype)

- No authentication - single hardcoded `learner_id="default"`.
- No horizontal scaling story beyond "swap the background thread for a
  queue" (discussed, not built - see DESIGN_NOTE.md §Scale).
- The `DIAGRAM_TEXT` format is accepted end-to-end but the evaluators don't
  yet parse UML structure specially - they treat it as text, same as
  `TEXT_DESIGN`. Flagged as the natural next increment.
