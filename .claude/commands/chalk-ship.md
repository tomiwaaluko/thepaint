---
description: Phase 6 — write the deployment spec, get green, and open a PR into railway (never main).
---

Run **Phase 6 — Ship** of the Chalk Dev Flow.

Follow this workflow exactly: @.claude/workflows/06-ship.md

Produce `specs/<branch-slug>/deployment-spec.md` from
@.claude/templates/deployment-spec.md (target `railway`, migrations, Railway services,
env, model artifacts, rollout, rollback). Run the final green gate
(`pytest tests/ -v`, plus `npm run lint && npm run build` if the frontend was
touched). Update `TODO.md` and add a dated `CHANGELOG.md` entry per the CLAUDE.md
session rules.

Push the branch (`git push -u origin <prefix>/<slug>`) and open the PR with **base =
`railway`**, using `.github/PULL_REQUEST_TEMPLATE.md`. Do **not** open a PR into
`main`. Then run the mandatory CodeRabbit review flow: wait ~60s, fetch the review,
triage and fix actionable items, push, re-fetch, hand off with a summary.

Stop at this phase's Definition of Done.
