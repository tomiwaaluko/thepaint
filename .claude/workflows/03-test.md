# Workflow 03 — Test (write the tests first)

**Phase 3 of the Chalk Dev Flow.** Borrows from Superpowers `test-driven-development`.
Triggered by [`/chalk-test`](../commands/chalk-test.md).

The job of this phase: turn the specs into a **testing spec** and a set of **failing
tests** — the RED half of RED-GREEN-REFACTOR — *before* any implementation code
exists. Phase 4 makes them pass.

**Output:** `specs/<branch-slug>/testing-spec.md`
(template: [`testing-spec.md`](../templates/testing-spec.md)) + failing tests under
`tests/`.

---

## Why tests come before implementation

Superpowers' rule: write the failing test, watch it fail for the right reason, then
write the minimal code to pass. Code written before its test is deleted and redone.
This guarantees every line is covered and specified.

## Step 1 — Write the testing spec

From `implementation-spec.md`, enumerate:

- **Unit tests** — every public function gets one (Chalk testing standard).
- **The `as_of_date` leakage tests** — for *every* feature function, a test proving
  data with `game_date >= as_of_date` is never used. This is mandatory and
  non-negotiable.
- **Idempotency tests** — for ingestion, running the job twice yields identical DB
  state (upsert, not duplicate rows).
- **API tests** — `httpx.AsyncClient` against the FastAPI app; assert status codes,
  response schema, and error mappings. Override DB/Redis deps with mocks.
- **Validation tests** — walk-forward split respected; no future data in training
  folds.
- **Edge cases** — empty windows, missing players (three-tier resolution), playoff
  game-ids (`004` prefix), zero-games days, timeouts + CDN fallback.
- **Coverage target** — ≥ 80%.

Record each planned test (name, file, what it asserts) in `testing-spec.md`.

## Step 2 — Write the tests as failing tests

- Place files as `tests/test_<area>/test_<thing>.py` colocated by domain.
- Use `pytest` + `pytest-asyncio`; **never hit the real nba_api** — mock all external
  responses.
- Run them and confirm they fail *for the intended reason* (missing implementation),
  not an import typo:

```bash
pytest tests/test_<area>/ -v
```

Record the RED result in `testing-spec.md` under "RED baseline".

## Step 3 — Do NOT implement yet

Resist writing production code here. If a test can only be written after a signature
exists, add the minimal stub (function that `raise NotImplementedError`) — the test
still fails RED, and phase 4 fills the body.

---

## Definition of done for phase 3

- [ ] `testing-spec.md` lists every test with file, name, and assertion
- [ ] A failing `as_of_date` leakage test exists for each feature function
- [ ] Idempotency / API / walk-forward / edge-case tests written as specified
- [ ] `pytest` shows the new tests failing for the *right* reason (RED)
- [ ] No production logic written yet

Next: [`/chalk-implement`](../commands/chalk-implement.md) →
[`04-implement.md`](04-implement.md).
