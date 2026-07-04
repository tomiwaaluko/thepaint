---
description: Phase 5 — simplify the fresh diff, then review it against the specs and non-negotiables.
---

Run **Phase 5 — Simplify & Review** of the Chalk Dev Flow.

Follow this workflow exactly: @.claude/workflows/05-simplify-and-review.md

**Part A — Simplify:** clean the diff for reuse, dead code, altitude, and naming;
re-run tests after each change (GREEN stays GREEN). Use the `/simplify` skill if
available.

**Part B — Review:** check the diff against both the specs and the Chalk
non-negotiables, reporting findings by severity. The highest-priority check is the
`as_of_date` leakage gate on every feature function. Also verify upsert/idempotency,
async, one-model-per-stat, API/DB contract match, and security rules.

**Part C — Independent review:** for non-trivial changes, dispatch a fresh read-only
review subagent (or use `/code-review`) so a cold reviewer sees the diff.

**Part D — Triage:** fix blocking issues now and re-review; record nits as follow-ups.
Stop at this phase's Definition of Done with no blocking findings remaining.
