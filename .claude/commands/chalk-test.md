---
description: Test-only workflow — branch off railway, add/fix tests for existing code, verify they pass and actually assert, ship (PR into railway). Loops back on failure.
argument-hint: "<what to test>"   (optional)
---

# chalk-test

> Add or repair tests for **existing** behavior — meaningful, passing, and shipped
> through `railway`.

Branch off `railway`, never `main`. Here the "work" *is* the tests — you are not
changing product code (if you must, that's a `bugfix`/`feature`). Scaffold
`specs/test-<name>/`; the primary spec is `testing-spec.md`.

## MCP Integration
Prefer connected MCP servers (GitHub MCP + CodeRabbit always available).
- **Trackers:** link the coverage/QA ticket; post PR link.
- **Git hosting / CI:** open PR, poll the test job, read failing logs; check coverage
  reporting if the CI exposes it.
Only use connected servers; else `git` + GitHub MCP.

## Resuming
- **Branch cut from `railway`?** → skip step 1.
- **Tests written, working tree dirty?** → resume at step 3 (verify).
- **Pushed with a PR open?** → resume at step 4 (pipeline check).

## Steps

1. **Create a test branch**
   - `git fetch origin railway` → `git switch --create test/<name> origin/railway`.
   - Scaffold `specs/test-<name>/`; record baseline `pytest`.

2. **Write the tests** (`chalk-work` skill, tests-only mode)
   - Plan them in `testing-spec.md`, then write them. Cover the mandatory Chalk
     categories where relevant: **`as_of_date` leakage per feature function**,
     idempotency, `httpx.AsyncClient` API tests, walk-forward, edge cases (missing
     player, playoff `004`, timeouts + CDN fallback). Mock nba_api; no secrets in
     fixtures.

3. **Verify the tests are meaningful**
   - They must **pass against current code** and **actually assert** — sanity-check by
     temporarily breaking the code under test and confirming the test goes red, then
     revert. Aim to move coverage toward ≥ 80%.
   - **Loop-back:** a test doesn't fail when it should → strengthen the assertion.
     **Loop cap 3** → ask the user.

4. **Ship** (`chalk-ship` skill)
   - Invoke `chalk-ship`: `deployment-spec.md` (usually "tests only, no service impact"),
     housekeeping, push, PR with **base = `railway`** (never `main`).
   - **Pipeline check (MCP):** on failure read logs → **step 2/3**. **Loop cap 3** → ask
     user. On pass, CodeRabbit triage.

5. **Compound (optional)** — run `chalk-compound` if you built a reusable fixture/pattern
   worth documenting.
