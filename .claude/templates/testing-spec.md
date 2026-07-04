# Testing Spec — <feature title>

> Tests written *before* implementation (RED). Owned by phase 3 (`/chalk-test`).

| | |
|---|---|
| **Branch** | `<prefix>/<slug>` |
| **Date** | YYYY-MM-DD |
| **Implementation spec** | ./implementation-spec.md |
| **Coverage target** | ≥ 80% |

## Planned tests
| ID | File | Test name | Asserts |
|---|---|---|---|
| U1 | `tests/test_<area>/test_<x>.py` | `test_...` | ... |

## Mandatory categories

### as_of_date leakage (one per feature function)
For each feature fn, a test proving data with `game_date >= as_of_date` is never used.
- [ ] `test_<fn>_respects_as_of_date` — insert a future-dated log, assert it is excluded

### Idempotency (ingestion)
- [ ] running the job twice yields identical DB state (upsert, no dup rows)

### API (`httpx.AsyncClient`)
- [ ] status codes, response schema, error mappings; DB/Redis deps mocked

### Validation
- [ ] walk-forward split honored; no future data in training folds

### Edge cases
- [ ] empty rolling windows · missing player (three-tier resolution) · playoff
  game-id (`004`) · zero-games day · timeout + CDN fallback

## Mocking policy
Never hit the real nba_api. Mock all external responses. No secrets in fixtures.

## RED baseline
`pytest tests/test_<area>/ -v` output at end of phase 3 — every new test failing for
the intended (not-yet-implemented) reason:

```
<paste RED summary: N failed>
```

## GREEN target (filled in phase 4)
```
<paste GREEN summary: N passed; coverage %>
```
