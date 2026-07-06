---
name: chalk-work
description: Phase skill — execute the implementation plan test-first (RED → GREEN → simplify), one task at a time. Produces the testing spec and passing code. Invoked by the chalk-* branch workflows.
---

# chalk-work

> Build the plan test-first: write the failing test, make it pass, simplify, commit —
> one task at a time.

Reads `specs/<branch-slug>/implementation-spec.md`. Produces
`specs/<branch-slug>/testing-spec.md` (template `.claude/templates/testing-spec.md`)
and the passing implementation.

## MCP (optional)
If a tracker MCP is connected, keep the ticket current. No MCP is required for this
phase.

## Per-task rhythm (RED → GREEN → REFACTOR)
Walk the task list in `implementation-spec.md` top to bottom. For each task:

1. **RED** — write the test(s) first and watch them fail for the *right* reason (not an
   import typo). Record the planned tests in `testing-spec.md`.
2. **GREEN** — write the smallest code that makes them pass. Nothing speculative.
3. **REFACTOR / simplify** — remove duplication and dead code, prefer existing helpers
   in `chalk/`, put logic at the right layer; re-run tests (GREEN stays GREEN).
4. **Commit** — one focused commit per task, imperative subject.
5. **Tick the box** in `implementation-spec.md`.

## Mandatory tests (from `CLAUDE.md`)
- **`as_of_date` leakage test for every feature function** — future-dated rows are
  never used. Non-negotiable.
- **Idempotency** — running an ingestion job twice yields identical DB state.
- **API** — `httpx.AsyncClient`, status codes, response schema, error mapping; DB/Redis
  mocked.
- **Walk-forward** — no future data in training folds.
- **Edge cases** — empty windows, missing player (three-tier resolution), playoff
  game-id `004`, zero-games day, timeout + CDN fallback.
- Never hit the real nba_api — mock everything. Coverage target ≥ 80%.

## Non-negotiables while coding
`as_of_date` on every feature fn (`game_date < as_of_date`); upsert never plain INSERT;
async all the way down; one model per stat; walk-forward not k-fold; `structlog` +
custom exceptions (log before re-raise); match surrounding style.

## Internal loop (with a cap)
- Test fails after a GREEN attempt → fix and retry **within this phase**.
- If **3 rounds** pass with no progress on the same task → stop and report to the
  calling workflow so it can decide (loop back to `chalk-plan`, or ask the user).
- If implementation reveals the design was wrong → update the specs and report back;
  the workflow may loop to `chalk-plan`.

## Optional: subagent-driven
For a large plan, dispatch a fresh subagent per task with its exact spec, then two-stage
check the output (spec-compliance, then quality) before folding it in. Straight-line
implementation is fine for small changes.

## Done when
- [ ] Every planned test passes: `pytest tests/ -v` GREEN
- [ ] All `implementation-spec.md` tasks checked off; specs match the code
- [ ] Non-negotiables upheld; `testing-spec.md` RED baseline + GREEN result recorded
