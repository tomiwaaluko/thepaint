# Contributing to Chalk

Thanks for your interest in contributing.

## Before You Start

- Read `README.md` for setup and project context.
- Review repository conventions in `AGENTS.md`.
- Open an issue first for larger changes so scope is aligned before implementation.

## Development Setup

1. Install backend dependencies (pinned via the lockfiles):

```bash
pip install -r requirements-dev.txt
pip install --no-deps -e .
```

2. Create environment file:

```bash
copy .env.example .env
```

3. Run migrations:

```bash
alembic upgrade head
```

4. Run API:

```bash
uvicorn chalk.api.main:app --reload --port 8000
```

5. Optional frontend setup:

```bash
cd dashboard
npm install
npm run dev
```

## Branch and PR Workflow

- Create a feature branch from the active development branch.
- Keep PRs focused and reasonably small.
- Use clear commit messages (imperative style).
- Link related issues in the PR description.

## Testing Requirements

Before opening a PR, run:

```bash
ruff check .
pytest tests/ -v
```

If you touched frontend code, also run:

```bash
cd dashboard
npm run lint
npm run build
```

CI (`.github/workflows/ci.yml`) runs the same checks on every PR into
`railway` and `main` — PRs must be green before merge.

## Updating Dependencies

Dependency versions are declared as ranges in `pyproject.toml` and pinned in
`requirements.txt` (production) and `requirements-dev.txt` (dev/CI). The
Docker image installs only from `requirements.txt`. To upgrade or add a
dependency:

```bash
# Edit pyproject.toml first, then regenerate both lockfiles:
uv pip compile pyproject.toml -o requirements.txt --python-version 3.11
uv pip compile pyproject.toml --extra dev -o requirements-dev.txt --python-version 3.11
```

Commit `pyproject.toml` and both lockfiles together. Be careful with
`xgboost`, `lightgbm`, and `scikit-learn` — the committed `models/*.joblib`
artifacts must still load under the new versions (start the API and check
for `model_load_failed` warnings).

## Coding Standards

- Python: PEP 8, type hints where practical, `snake_case` for functions/modules.
- TypeScript/React: `PascalCase` components, `useX` hook naming, keep shared types in `dashboard/src/types/`.
- Keep code changes minimal and avoid unrelated refactors in the same PR.

## Critical Domain Rules

- Never introduce data leakage in features.
- Any feature-generation logic must respect `as_of_date` boundaries.
- Do not use random k-fold CV for sports time series.

## Security and Secrets

- Never commit secrets (`.env`, API keys, credentials).
- Do not include production tokens or private URLs in test fixtures.

## Reporting Issues

- Use issue templates where possible.
- Include expected behavior, actual behavior, and reproducible steps.
- Add logs, screenshots, or tracebacks when helpful.
