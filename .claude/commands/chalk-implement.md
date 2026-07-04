---
description: Phase 4 — write minimal code to turn the phase-3 tests green, one task at a time.
---

Run **Phase 4 — Implement** of the Chalk Dev Flow.

Follow this workflow exactly: @.claude/workflows/04-implement.md

Execute the task list in `specs/<branch-slug>/implementation-spec.md` top to bottom.
For each task: confirm its test is RED, write the smallest code to make it GREEN,
run the tests, commit with an imperative subject, tick the box.

Uphold the non-negotiables: `as_of_date` on every feature function, upsert (never
plain INSERT), async all the way down, one model per stat, walk-forward validation,
`structlog` + custom exceptions. For a large plan, optionally dispatch a subagent per
task with a two-stage (spec-compliance then quality) check — otherwise straight-line
implementation is fine.

If the design proves wrong mid-flight, update the specs. Stop at this phase's
Definition of Done with the full suite green.
