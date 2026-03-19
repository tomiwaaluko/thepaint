---
name: railway-deployment
description: Use this skill when working on Railway deployment configuration, cron job setup, environment variables, private networking between services, or Supabase connection setup. Covers railway.json config files, cron service patterns, Railway private networking, and the difference between local Docker and Railway+Supabase production.
---

# Railway Deployment Skill

## Project Service Map

| Service Name | Type | Purpose |
|---|---|---|
| `web` | Web service | FastAPI API (chalk/api/main.py) |
| `thepaint` | Web service | React frontend (dashboard/) |
| `Redis` | Redis add-on | Shared cache for all services |
| `ingest` | Cron job | Daily data ingestion at 07:00 UTC |
| `prediction` | Cron job | Daily prediction generation at 18:00 UTC |

---

## Railway Config File Format

Each service points to its own config file in the repo root.

```json
// railway.json — API service
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": { "builder": "DOCKERFILE", "dockerfilePath": "Dockerfile" },
  "deploy": {
    "startCommand": "sh -c \"uvicorn chalk.api.main:app --host 0.0.0.0 --port ${PORT:-8000}\"",
    "healthcheckPath": "/v1/health",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 3
  }
}

// railway.ingest.json — ingest cron
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": { "builder": "DOCKERFILE", "dockerfilePath": "Dockerfile" },
  "deploy": {
    "cronSchedule": "0 7 * * *",
    "startCommand": "python scripts/railway_ingest.py",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 2
  }
}

// railway.predict.json — prediction cron
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": { "builder": "DOCKERFILE", "dockerfilePath": "Dockerfile" },
  "deploy": {
    "cronSchedule": "0 18 * * *",
    "startCommand": "python scripts/railway_predict.py",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 1
  }
}
```

---

## Environment Variables Per Service

### `web` (API)
```
DATABASE_URL   = postgresql+asyncpg://...@aws-1-us-east-1.pooler.supabase.com:5432/postgres
REDIS_URL      = redis://default:<password>@redis.railway.internal:6379
ALLOWED_ORIGINS = https://thepaint-production.up.railway.app
LOG_LEVEL      = INFO
ODDS_API_KEY   = <key>
MLFLOW_TRACKING_URI = (leave blank or point at a deployed MLflow service)
NBA_API_CACHE_DIR = .cache/nba_api
```

### `ingest` (Cron)
```
DATABASE_URL   = (same as web)
REDIS_URL      = (same as web)
ODDS_API_KEY   = (same as web)
```

### `prediction` (Cron)
```
DATABASE_URL      = (same as web)
REDIS_URL         = (same as web)
ODDS_API_KEY      = (same as web)
API_INTERNAL_URL  = http://web.railway.internal:8000
```

---

## Railway Private Networking

Services within the same Railway project communicate via:
```
http://<service-name>.railway.internal:<port>
```

The service name is the name shown in the Railway dashboard (lowercase).
- API internal URL: `http://web.railway.internal:8000`
- Redis internal URL: auto-injected as `redis://default:<pw>@redis.railway.internal:6379`

**Never use public URLs for service-to-service calls** — private networking is faster and free.

---

## Database: Supabase Session Pooler

Use the **Session Pooler** connection string (NOT Direct Connection, NOT Transaction Pooler).

- Session Pooler: `postgresql+asyncpg://postgres:<pw>@aws-1-us-east-1.pooler.supabase.com:5432/postgres`
- Direct Connection: **avoid** — not IPv4 compatible on Railway
- Transaction Pooler (port 6543): **avoid** — breaks asyncpg prepared statements

The Session Pooler URL is found in Supabase → Settings → Database → Connection String → Method: Session Pooler.

---

## Cron Job Behavior

Railway cron jobs are **not persistent services**. They:
1. Spin up a container at the scheduled time
2. Run the start command
3. Exit (success = exit 0, failure = exit 1)
4. Show as "Deployment successful" or "Deployment crashed" in Activity

This is **expected behavior** — a "crashed" cron means the script exited with an error.
A "successful" cron means it ran and completed cleanly.

Cron services do **not** have a restart policy (Railway enforces this).

---

## Standalone Cron Scripts

Each cron script (`scripts/railway_ingest.py`, `scripts/railway_predict.py`) is self-contained:
- No Airflow dependencies
- Uses `asyncio.new_event_loop()` to run async code
- Exits with `sys.exit(1)` on any step failure
- Logs with `structlog`

The scripts import `chalk.*` — the Dockerfile must install the package (`pip install -e .`).

---

## Adding a New Cron Job

1. Write the standalone script in `scripts/railway_<name>.py`
2. Create `railway.<name>.json` in the repo root with the cron schedule
3. In Railway dashboard: New Service → GitHub Repo → same repo
4. Settings → Config-as-code → set to `/railway.<name>.json`
5. Add required env vars (at minimum: `DATABASE_URL`, `REDIS_URL`)
6. Deploy

---

## Differences: Local Docker vs Railway

| Concern | Local Docker | Railway + Supabase |
|---|---|---|
| Database | TimescaleDB (local) | Supabase PostgreSQL (session pooler) |
| Redis | `redis://localhost:6379/0` | `redis://...@redis.railway.internal:6379` |
| Scheduling | Airflow (docker-compose) | Railway cron services |
| Model files | Persisted in Docker volume | Baked into Docker image (committed to git) |
| nba_api cache | `.cache/` persists on disk | Ephemeral (lost on restart — fallback to API) |
| MLflow | Docker service at :5000 | Not deployed (tracking disabled in prod) |
| Hot reload | uvicorn --reload + volume mount | Static image, redeploy required |
