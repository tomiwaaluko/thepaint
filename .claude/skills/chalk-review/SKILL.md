---
name: chalk-review
description: Phase skill — simplify the fresh diff, then review it against the specs and the Chalk non-negotiables, reporting findings by severity. Invoked by the chalk-* branch workflows.
---

# chalk-review

> Clean the diff, then review it against the plan — a cold reviewer catches what the
> author rationalized away.

Reviews the working diff for `specs/<branch-slug>/`. Fixes blocking issues; records
nits.

## Part A — Simplify (quality only)
Reuse existing helpers, remove dead code / needless indirection, fix altitude (feature
math in `features/`, not a route handler), and naming
(`snake_case`/`PascalCase`/`UPPER_SNAKE_CASE`; MLflow `tha_paint/{stat}/{model_type}`).
Re-run tests after each change — GREEN stays GREEN. Use the repo `/simplify` skill if
available.

## Part B — Review against the plan (report by severity)
**Correctness & domain (blocking):**
- [ ] `as_of_date` gate correct on every feature function — **no data leakage** (highest priority)
- [ ] Ingestion uses upsert; re-running is idempotent
- [ ] Async all the way down; one model per stat; walk-forward not k-fold
- [ ] Errors raised as custom exceptions and logged before re-raise

**Contract & security (blocking):**
- [ ] API matches the implementation-spec API spec (routes, schemas, status, caching)
- [ ] DB changes match the DB spec; migration has a working down-path
- [ ] Security rules honored: no secrets, input validated, params bound, CORS sane

**Quality (non-blocking unless egregious):**
- [ ] Tests meaningful, ≥ 80% coverage, edge cases covered; naming/style/docs match

## Part C — Independent pass (recommended)
For non-trivial changes, dispatch a fresh read-only review subagent (or use
`/code-review`) with the diff + specs so it reviews with no memory of writing the code.

## Loop-back (this is where loop-engineering lives)
- **Code-level blocking issue** → report back so the workflow loops to `chalk-work`.
- **Design-level flaw** (the plan itself is wrong) → report back so the workflow loops
  to `chalk-plan`.
- **Nits** → fix if fast, else record under "Known follow-ups" in the deployment spec.
- Do not pass review with blocking findings open.

## Done when
- [ ] Diff simplified; tests GREEN
- [ ] Review complete; all blocking findings resolved (or escalated via loop-back)
- [ ] Independent pass done for non-trivial changes; nits recorded, not lost
