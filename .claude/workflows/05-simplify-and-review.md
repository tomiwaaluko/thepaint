# Workflow 05 — Simplify & Review

**Phase 5 of the Chalk Dev Flow.** Borrows from Compound Engineering `ce-simplify-code`
+ `ce-code-review` and Superpowers `requesting-code-review`. Triggered by
[`/chalk-review`](../commands/chalk-review.md).

The job of this phase: clean the freshly written code for clarity and reuse, then
review the whole diff against the specs before it goes near a PR.

**Output:** a reviewed, simplified diff. Findings logged; blocking issues fixed.

---

## Part A — Simplify (do this first, while it's fresh)

Refine the diff for quality *only* — this is not a bug hunt (that's Part B):

- **Reuse** — is there an existing helper in `chalk/` this duplicates? Prefer it.
- **Simplify** — remove dead code, collapse needless indirection, drop speculative
  generality.
- **Altitude** — is logic at the right layer? Feature math in `features/`, not in a
  route handler.
- **Naming** — `snake_case` funcs, `PascalCase` classes, `UPPER_SNAKE_CASE`
  constants; MLflow names per the `tha_paint/{stat}/{model_type}` convention.
- **Re-run tests** after each simplification — GREEN must stay GREEN.

The repo `/simplify` skill covers exactly this if available.

## Part B — Review against the plan

Review the diff the way a senior engineer would, checking it against **both** the
specs and the Chalk non-negotiables. Report findings by severity.

**Correctness & domain (blocking):**
- [ ] `as_of_date` gate present and correct on every feature function — **no data
      leakage**. This is the single highest-priority check.
- [ ] Ingestion uses upsert; re-running is idempotent.
- [ ] Async all the way down; no sync DB calls in the hot path.
- [ ] One model per stat; walk-forward validation, not k-fold.
- [ ] Errors raised as custom exceptions and logged before re-raise.

**Contract & security (blocking):**
- [ ] API matches the `implementation-spec.md` API spec (routes, schemas, status
      codes, caching).
- [ ] DB changes match the DB spec; migration has a working down-path.
- [ ] Security rules honored: no secrets committed, input validated, params
      bound, CORS/origins sane.

**Quality (non-blocking unless egregious):**
- [ ] Tests meaningful and ≥ 80% coverage; edge cases covered.
- [ ] Naming/style match the codebase; docs/specs updated.

## Part C — Subagent review (recommended)

Dispatch a fresh, read-only review subagent (`Explore` or a general reviewer) with
the diff + the specs so it reviews with *no memory of having written the code* — a
cold reviewer catches what the author rationalized away. Two independent passes
(spec-compliance, then code-quality) mirror the Superpowers two-stage review.

The repo `/code-review` skill can drive this if available.

## Part D — Triage & fix

- **Blocking issues** → fix now, re-run tests, re-review the fix.
- **Nits** → fix if fast; otherwise note in `deployment-spec.md` "Known follow-ups".
- Loop Part B until no blocking issues remain.

---

## Definition of done for phase 5

- [ ] Diff simplified; tests still GREEN
- [ ] Full review completed; all blocking findings resolved
- [ ] Independent (subagent) review pass done for non-trivial changes
- [ ] Remaining nits recorded as follow-ups, not lost

Next: [`/chalk-ship`](../commands/chalk-ship.md) → [`06-ship.md`](06-ship.md).
