---
description: Run the full Chalk Dev Flow — branch off railway, then brainstorm → plan → test → implement → review → ship → compound.
argument-hint: <prefix> "<short description>"   e.g. feature "opponent usage-rate feature"
---

You are driving the **Chalk Dev Flow** end to end. Arguments: `$ARGUMENTS`
(first token = branch prefix, remainder = the work description).

Read the flow overview first: @.claude/README.md

Then execute the phases **in order**, honoring each phase's Definition of Done before
moving on. Do not skip a phase; if a phase produces nothing (e.g. no DB changes), say
so explicitly in its spec rather than omitting it.

1. **Phase 0 — Branch** → @.claude/workflows/00-branch-naming.md
   Cut `<prefix>/<slug>` from `railway`, scaffold `specs/<branch-slug>/` from the
   templates, confirm a green baseline. **Never branch from or commit to `main`.**
2. **Phase 1 — Brainstorm** → @.claude/workflows/01-brainstorm.md → `planning-spec.md`
3. **Phase 2 — Plan & Design** → @.claude/workflows/02-plan-and-design.md →
   `design-spec.md` + `implementation-spec.md` (API/DB/security)
4. **Phase 3 — Test** → @.claude/workflows/03-test.md → `testing-spec.md` + failing tests
5. **Phase 4 — Implement** → @.claude/workflows/04-implement.md → GREEN
6. **Phase 5 — Simplify & Review** → @.claude/workflows/05-simplify-and-review.md
7. **Phase 6 — Ship** → @.claude/workflows/06-ship.md → `deployment-spec.md` + PR into `railway`
8. **Phase 7 — Compound** → @.claude/workflows/07-compound.md → `docs/solutions/` entry

Pause for the user between phases when a decision genuinely needs their input
(use AskUserQuestion), otherwise proceed with sensible defaults and tell them what you
chose. Keep the five specs in `specs/<branch-slug>/` in sync with reality at every
step.
