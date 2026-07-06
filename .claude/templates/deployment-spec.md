# Deployment Spec — <feature title>

> How this ships. Owned by phase 6 (`/chalk-ship`).

| | |
|---|---|
| **Branch** | `<prefix>/<slug>` |
| **Date** | YYYY-MM-DD |
| **Merge target** | **`railway`** (never `main`) |
| **PR** | #NNN |

## Migrations
- Alembic revisions run (in order): `...`
- Down-path / rollback: `alembic downgrade <rev>`

## Railway services affected
| Service | Type | Change |
|---|---|---|
| `web` | FastAPI | |
| `thepaint` | React frontend | |
| `ingest` | Cron 07:00 UTC | |
| `prediction` | Cron 18:00 UTC | |
| `Redis` | add-on | |

- Shared Docker image / start-command changes: `...`
- Builder: **`DOCKERFILE`** for Python services (not Railpack).

## Config / env
- New env vars (added to `.env.example` **and** the Railway service): `...`
- Redis URL via `${{Redis.REDIS_URL}}`; DB via Supabase **Session Pooler**.

## Model artifacts
MLflow is not deployed in prod — model files committed to git and loaded from disk.
Files added/updated: `models/...`

## Rollout & verification
- Post-merge checks: health endpoint, sample `/v1/...` call, cron log check.
- Latency budget confirmed: p99 < 500ms.

## Rollback plan
- Revert the merge on `railway`; run migration down-path; redeploy affected services.

## Pre-ship gate
- [ ] `pytest tests/ -v` green
- [ ] `npm run lint && npm run build` green (if frontend touched)
- [ ] `TODO.md` + `CHANGELOG.md` updated
- [ ] All five specs match final code

## Known follow-ups
Nits deferred from review; future work.
