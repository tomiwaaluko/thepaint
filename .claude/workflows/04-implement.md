# Workflow 04 — Implement

**Phase 4 of the Chalk Dev Flow.** Borrows from Compound Engineering `ce-work` and
Superpowers `subagent-driven-development` + the GREEN half of TDD. Triggered by
[`/chalk-implement`](../commands/chalk-implement.md).

The job of this phase: write the **minimal code to turn the phase-3 tests GREEN**,
one task at a time, exactly as laid out in `implementation-spec.md`.

**Output:** passing implementation. No new spec file — this phase *executes* the
implementation spec.

---

## Working rhythm (per task)

Walk the task list in `implementation-spec.md` top to bottom. For each task:

1. **RED already exists** (from phase 3) — confirm the relevant test is failing.
2. **GREEN** — write the smallest code that makes it pass. Nothing speculative.
3. **Verify** — run the task's tests:
   ```bash
   pytest tests/test_<area>/ -v
   ```
4. **Commit** — one focused commit per task, imperative subject
   (`Add opponent usage-rate rolling feature`). Small commits keep the diff
   reviewable and the branch bisectable.
5. **Tick the box** in `implementation-spec.md`.

## Non-negotiables while coding

Pulled from `CLAUDE.md` — a reviewer *will* reject violations:

- **`as_of_date` on every feature function**, filtering `game_date < as_of_date`.
- **Upsert, never plain INSERT** in ingestion (`ON CONFLICT DO UPDATE`).
- **Async all the way down** — `async def` handlers, asyncpg sessions, no sync DB
  calls in the hot path.
- **One model per stat** — no multi-output models.
- **Walk-forward validation only** — never random k-fold.
- **Structured logging** via `structlog`; never swallow an exception silently — log
  before re-raising. Raise the custom `IngestError` / `FeatureError` /
  `PredictionError`.
- **Match surrounding style** — naming conventions from `CLAUDE.md`, type hints,
  comment density of neighboring code.

## Subagent-driven option (for larger plans)

For a plan with many independent tasks, dispatch a fresh subagent per task (or per
small batch) with the task's exact spec, then run a two-stage check on its output:

1. **Spec compliance** — did it build exactly what the task said, no more?
2. **Code quality** — does it match repo idioms and pass the non-negotiables?

Fold approved work back in; reject and re-dispatch anything that drifts. Keep
orchestration and final judgment in the main thread. This is optional — for a small
change, straight-line step-by-step implementation is perfectly effective.

## Keep specs honest

If implementation reveals the design was wrong, **update `design-spec.md` /
`implementation-spec.md`** rather than silently diverging. The specs must match the
code at merge time.

---

## Definition of done for phase 4

- [ ] Every phase-3 test now passes (GREEN): `pytest tests/ -v`
- [ ] All `implementation-spec.md` tasks checked off
- [ ] Non-negotiables upheld (spot-check `as_of_date`, upsert, async, per-stat models)
- [ ] Specs updated to reflect any mid-flight design changes
- [ ] One focused commit per task on the correct `<prefix>/<slug>` branch

Next: [`/chalk-review`](../commands/chalk-review.md) →
[`05-simplify-and-review.md`](05-simplify-and-review.md).
