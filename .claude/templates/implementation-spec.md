# Implementation Spec — <feature title>

> The buildable plan, including **API spec**, **DB spec**, and **security rules**.
> Owned by phase 2 (`/chalk-plan`); executed by phase 4 (`/chalk-implement`).

| | |
|---|---|
| **Branch** | `<prefix>/<slug>` |
| **Date** | YYYY-MM-DD |
| **Design spec** | ./design-spec.md |

## Task breakdown
Bite-sized tasks (2–5 min each). One commit per task.

- [ ] **T1** — `path/to/file.py` — <exact change> — verify: `pytest tests/... -v`
- [ ] **T2** — ... — verify: ...
- [ ] **T3** — ...

---

## API spec
> Mark "No API changes" if none.

- **Route(s):** `/v1/{resource}/{id}/{action}` — e.g. `POST /v1/players/2544/predict`
- **Method / params:** path params, query params
- **Request body:** Pydantic schema
- **Response:** Pydantic schema (fields + types)
- **Status codes:** 200 / 4xx / 5xx and the error mapping
  (`IngestError`/`FeatureError`/`PredictionError` → HTTP)
- **Async:** all handlers `async def`
- **Caching:** Redis key, 15-min TTL, injury-update invalidation
- **Latency budget:** p99 < 500ms

---

## DB spec
> Mark "No DB changes" if none.

- **Tables touched:** (players / teams / games / player_game_logs / team_game_logs /
  injuries / betting_lines / predictions / new)
- **Columns added/changed:** name — type — nullable — default
- **Migration:** `alembic/versions/<rev>_<slug>.py` — up + down described
- **Indexes / TimescaleDB:** hypertable / index considerations
- **Idempotency:** writes use `INSERT … ON CONFLICT (<target>) DO UPDATE`. Conflict
  target: `...`

---

## Security rules
> Always complete.

- **Secrets:** no keys/tokens in code, tests, or fixtures; config via
  `pydantic-settings` / `.env` only.
- **Input validation:** Pydantic validates all external input; parameterized queries
  only.
- **CORS / origins:** `ALLOWED_ORIGINS` validated if touching API startup.
- **Leakage-as-integrity:** functions that must enforce the `as_of_date` gate:
  `...`
- **PII / least privilege:** player PII handling and access scope: `...`
- **Dependencies:** new deps pinned and vetted: `...`

---

## Execution notes
Anything phase 4 needs to know: ordering constraints, feature flags, backfill steps
(`scripts/backfill.py`), retraining (`scripts/train_all.py`).
