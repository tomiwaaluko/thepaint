---
description: Phase 7 — capture the loop's learnings into docs/solutions so the next loop starts smarter.
---

Run **Phase 7 — Compound** of the Chalk Dev Flow.

Follow this workflow exactly: @.claude/workflows/07-compound.md

Harvest the learnings from this branch's five specs and the PR discussion, then write
`docs/solutions/<YYYY-MM-DD>-<branch-slug>.md` covering: context, what we learned,
reusable patterns, traps & gotchas (especially leakage/idempotency), and guidance for
the next loop.

Promote any durable learning beyond the one-off doc — a recurring domain rule into
`CLAUDE.md`, a module technique into the relevant `.agents/skills/*/SKILL.md`, or a
repeated review miss into the phase-5 checklist — as small, separately-scoped
follow-ups (their own `docs/` or `chore/` branch), not smuggled into the feature PR.

Confirm `CHANGELOG.md` + `TODO.md` are final. Stop at this phase's Definition of Done.
