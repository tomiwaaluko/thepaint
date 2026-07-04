---
description: Phase 2 — turn the planning spec into design + implementation specs (API, DB, security).
---

Run **Phase 2 — Plan & Design** of the Chalk Dev Flow.

Follow this workflow exactly: @.claude/workflows/02-plan-and-design.md

Read `specs/<branch-slug>/planning-spec.md` first, then produce **two** documents:

- `specs/<branch-slug>/design-spec.md` from @.claude/templates/design-spec.md —
  approach, components (real paths), data flow, decisions, interfaces (every feature
  function carries `as_of_date`).
- `specs/<branch-slug>/implementation-spec.md` from
  @.claude/templates/implementation-spec.md — bite-sized tasks **plus** the three
  mandatory sub-sections: **API spec**, **DB spec**, **security rules**. Mark any of
  the three "No changes" if genuinely none.

Honor idempotent-upsert and walk-forward-validation on paper. Stop at this phase's
Definition of Done and summarize both specs.
