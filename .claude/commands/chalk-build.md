---
description: Build-system / dependency-tooling workflow — branch off railway, change build config, verify a clean build + green tests, ship (PR into railway). Loops back on failure.
argument-hint: "<what build change>"   (optional)
---

# chalk-build

> Change the build system or dependency tooling — proven by a clean build — shipped
> through `railway`.

Branch off `railway`, never `main`. Scaffold `specs/build-<name>/`; fill
`planning-spec.md`, `implementation-spec.md` (build/deps config + security rules: pinned,
vetted deps), and `deployment-spec.md`.

## MCP Integration
Prefer connected MCP servers (GitHub MCP + CodeRabbit always available).
- **Git hosting / CI:** open PR, poll the build job, read failing logs.
- **Dependency/security-advisory MCP (if connected):** vet new/updated deps.
- **Trackers:** link the ticket; post PR link.
Only use connected servers; else `git` + GitHub MCP.

## Resuming
- **Branch cut from `railway`?** → skip step 1.
- **Config changed, working tree dirty?** → resume at step 3 (verify).
- **Pushed with a PR open?** → resume at step 4 (pipeline check).

## Steps

1. **Create a build branch**
   - `git fetch origin railway` → `git switch --create build/<name> origin/railway`.
   - Scaffold `specs/build-<name>/`; record baseline build/test state.

2. **Change the build config**
   - Edit `pyproject.toml` / `Dockerfile` / `docker-compose.yml` / `dashboard` build
     config as needed. Pin and vet dependencies. Keep Python-service images on the
     `DOCKERFILE` builder (Railpack misses the `chalk` package). Note env/tooling changes
     in `implementation-spec.md` + `.env.example`.

3. **Verify a clean build**
   - Reproduce a clean build: `pip install -e ".[dev]"` and `pytest tests/ -v`; for the
     frontend, `cd dashboard && npm install && npm run build`. Optionally `docker compose
     build`. Everything must succeed from clean.
   - **Loop-back:** build/tests fail → fix config here; if a dep is incompatible,
     reconsider (or ask the user). **Loop cap 3** → ask.

4. **Ship** (`chalk-ship` skill)
   - Invoke `chalk-ship`: `deployment-spec.md` (call out build/image impact on Railway
     services), housekeeping, push, PR with **base = `railway`** (never `main`).
   - **Pipeline check (MCP):** on failure read logs → **step 2/3**. **Loop cap 3** → ask
     user. On pass, CodeRabbit triage.

5. **Compound (optional)** — run `chalk-compound` if a build/dependency gotcha is worth
   recording.
