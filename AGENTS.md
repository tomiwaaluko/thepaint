# Repository Guidelines

## Project Structure & Module Organization
Backend code lives in `chalk/` (API routes, ingestion, features, models, predictions, monitoring).  
Frontend code lives in `dashboard/` (Vite + React + TypeScript app).  
Tests are under `tests/`, organized by domain (`test_api/`, `test_models/`, `test_features/`, etc.).  
Operational code and data live in `scripts/` (one-off jobs), `airflow/dags/` (local scheduling), `alembic/` (migrations), and `models/` (serialized model artifacts).

## Build, Test, and Development Commands
- `pip install -e ".[dev]"`: install backend + dev dependencies.
- `uvicorn chalk.api.main:app --reload --port 8000`: run FastAPI locally.
- `pytest tests/ -v`: run backend tests.
- `alembic upgrade head`: apply database migrations.
- `docker compose up`: bring up full local stack (db, redis, mlflow, api, airflow).
- `cd dashboard && npm install`: install frontend deps.
- `cd dashboard && npm run dev`: run dashboard locally.
- `cd dashboard && npm run build`: type-check and produce production build.
- `cd dashboard && npm run lint`: run ESLint for frontend.

## Coding Style & Naming Conventions
Python targets 3.11+ and follows PEP 8 style: 4-space indentation, `snake_case` for functions/modules, `PascalCase` for classes.  
Keep API schemas, route handlers, and model code strongly typed where practical.  
Frontend uses TypeScript + ESLint (`dashboard/eslint.config.js`): components in `PascalCase` (e.g., `GameCard.tsx`), hooks in `useX` form (e.g., `useGameSlate.ts`), and shared types in `dashboard/src/types/`.

## Testing Guidelines
Use `pytest` (with `pytest-asyncio` for async tests). Name files `test_*.py` and colocate by feature area (`tests/test_api/test_health.py`, etc.).  
For API changes, add route-level tests and dependency override/mocking for DB/Redis where needed. Run `pytest tests/ -v` before opening a PR.

## Commit & Pull Request Guidelines
Recent history favors short, imperative commit subjects (e.g., `Fix NBA API headers...`), with optional prefixes like `fix:`.  
PRs should include:
- clear summary of behavior changes,
- linked issue (if applicable),
- test evidence (commands run),
- screenshots or short clips for dashboard UI changes.

## Security & Configuration Tips
Copy `.env.example` to `.env` for local setup. Never commit secrets or API keys.  
Validate CORS and env-driven settings (`ALLOWED_ORIGINS`, DB/Redis URLs) when touching API startup or deployment configs.
