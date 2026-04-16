# Contributing to Chalk

Thanks for your interest in contributing.

## Before You Start

- Read `README.md` for setup and project context.
- Review repository conventions in `AGENTS.md`.
- Open an issue first for larger changes so scope is aligned before implementation.

## Development Setup

1. Install backend dependencies:

```bash
pip install -e ".[dev]"
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
pytest tests/ -v
```

If you touched frontend code, also run:

```bash
cd dashboard
npm run lint
npm run build
```

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
