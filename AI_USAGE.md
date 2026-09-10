# AI Usage

Built with Claude (Anthropic) as a pair-programming / architecture partner.
Below are the meaningful decisions where AI suggested something and I
accepted, rejected, or modified it - not a log of every prompt.

## 1. Zero-dependency stdlib backend instead of Flask/FastAPI/Express

**Suggested:** Claude proposed building with a real framework by default
(Flask or Express), then flagged that both add a `pip`/`npm install` step
and, on Windows, a real risk of venv-activation and `node_modules`
path-length problems.
**Accepted, with a twist:** I asked it to use only the Python standard
library (`http.server`, `sqlite3`, `urllib`) instead. Slightly more
boilerplate in `server.py`'s routing, but the whole project runs with
`python server.py` and nothing else - no install step to fail during
grading on someone else's machine.
**Why:** reliability of the demo mattered more than framework convenience
for a 2-day submission graders will actually try to run.

## 2. Evaluator interface as a Strategy pattern, not an if/else

**Suggested:** Claude's first draft had `EvaluationService` calling
deterministic checks and an AI call directly, inline.
**Rejected that shape**, asked for a shared `Evaluator` interface with
`DeterministicEvaluator` / `AIEvaluator` as separate implementations plus
a factory, specifically to answer the brief's "how would you add another
evaluation approach later" question concretely rather than just in prose.
**Why:** the assignment explicitly weights extensibility (10%) and
evaluation approach (15%); a class you can point to that demonstrates the
answer is more convincing than a paragraph claiming it's possible.

## 3. What happens when AI evaluation fails

**Suggested:** Claude's first version made any evaluator exception fail
the whole attempt.
**Modified:** changed it so the deterministic evaluator's results are kept
even if the AI evaluator throws (rate limit, missing API key, malformed
JSON) - the attempt still completes with a narrower rubric instead of
failing outright, and only fails if *every* evaluator fails.
**Why:** I didn't want a grader running this without an API key to see the
whole prototype look broken - graceful degradation felt like the more
honest way to handle "evaluation... fails" than an all-or-nothing error.

## 4. Async evaluation: background thread vs. making the user wait

**Suggested:** Claude first had submission evaluation run synchronously
inside the POST request - simplest possible code, but a slow AI call means
a slow/hanging request.
**Accepted a middle ground, rejected the extremes:** I didn't want a full
queue/worker setup (the brief explicitly says not to turn this into a
distributed-systems project), but a fully synchronous request felt wrong
too. Settled on: save the submission and return immediately, evaluate on a
background thread, frontend polls. Documented in `DESIGN_NOTE.md` as the
one thing I'd swap first at real scale.

## 5. Rubric aggregation when two evaluators score the same dimension

**Suggested:** Claude proposed just letting the AI evaluator's score always
win when both evaluators scored the same criterion.
**Rejected:** asked for a confidence-weighted average instead (deterministic
checks report confidence 1.0 since they're exact; AI reports its own
confidence), with the higher-confidence evaluator's qualitative text
(evidence/concern/suggestion) used for the learner-facing explanation.
**Why:** an unconditional "AI always wins" felt like it defeated the point
of having a deterministic check at all - the whole reason to split
evaluators is that neither one is fully trusted alone.

## What I did not take from AI suggestions

Claude also suggested adding a diagram-rendering submission format (actual
UML parsing) and a login/accounts system as part of the MVP. I cut both -
out of scope for a 2-day prototype per the brief's own scope boundary, and
`SubmissionFormat` / `learner_id` are already structured so they're easy
additions later without a redesign (see DESIGN_NOTE.md, "Trade-offs").
