# Research Note

## The learner problem

A learner can sit down, pick "design a Parking Lot," and produce *something*
- a page of classes, maybe a diagram - and still have no idea if it's good.
Unlike a DSA problem, there's no single correct answer to check against.
Two reasonable engineers can land on different class boundaries and both be
defensible, which means self-practice usually stalls at "I wrote it down"
rather than reaching "I know what to fix." That gap - between producing a
design and getting a *specific, evidence-based* verdict on it - is the
actual problem worth building for, not the UI around picking a problem.

## What's already out there

A short survey of existing LLD-practice tools and communities:

- **HelloInterview's Guided Practice** walks a learner step-by-step through
  a problem (requirements -> entities -> design) and gives per-step,
  rubric-based feedback tuned by interviewers, across an LLD-specific
  problem track (parking lots, elevators, rate limiters, etc.), alongside
  System Design and behavioral tracks.
- **AlgoMaster's LLD Practice** organizes ~45 problems into themed
  sections (state machines, management systems, payment systems, etc.) with
  AI-powered evaluation, and separately tracks a learner's history per
  problem.
- **LowLevelDesignMastery** leans visual-first: an in-browser playground
  with class-diagram tooling, multi-language code support, AI review, and
  spaced-repetition flashcards for pattern recall.
- **ashishps1/awesome-low-level-design** (23k+ GitHub stars) is the
  opposite end of the spectrum: a large curated list of problems and
  reference solutions with no submission or feedback loop at all - it's a
  reading list, not a practice loop.
- **Testlify** represents the assessment/ATS side of this space: a
  recruiter-facing skill test rather than a learner-facing practice tool.

## Gaps this MVP targets

1. Most tools that *do* give feedback treat it as a black-box score.
   Several of the tools above advertise "AI feedback" but the learner-facing
   examples emphasize a chat/conversation UI rather than a fixed, inspectable
   rubric - it's hard to tell if two attempts were judged the same way.
   This MVP forces every evaluator (deterministic or AI) through the same
   fixed rubric and requires each score to cite evidence from the
   submission, so feedback is comparable across attempts and explainable
   rather than a mystery number.
2. The free/list-based resources (awesome-low-level-design) have zero
   feedback loop; the polished commercial tools have a feedback loop but
   are closed products a two-day prototype can't inspect or extend. There's
   room for a small, transparent version that shows its rubric and its
   evaluation pipeline explicitly.
3. Retry/history is treated as a nice-to-have in most of these tools' public
   descriptions, but it's what turns "I solved a Parking Lot once" into
   deliberate practice. This MVP makes attempt history and retry first-class,
   not an afterthought.

## Product direction

A narrow, transparent loop: **5 problems, one submission format focus
(text design, with code and text-UML also accepted), a two-stage evaluator
(fast deterministic checks + judgement-heavy AI checks against a fixed,
shared rubric), and a visible attempt history.** Nothing about diagrams,
gamification, spaced repetition, or multi-language code execution - those
are exactly the "many features, weak practice logic" trap the assignment's
own guide warns against. The differentiator is that feedback is explainable
(evidence-per-dimension) and the evaluation pipeline is explicitly designed
to accept a third evaluator later without changing anything else.
