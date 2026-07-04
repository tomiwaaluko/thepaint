---
description: Maintenance workflow (deps, config, cleanup) — branch off railway, make the change, verify nothing breaks, ship (PR into railway). Loops back on failure.
argument-hint: "<what maintenance task>"   (optional)
---

# chalk-chore

> Maintenance with no behavior change — deps bumps, config, cleanup — verified safe and
> shipped through `railway`.

Branch off `railway`, never `main`. Lighter loop: no brainstorm/TDD gauntlet, but still
verified and reviewed. Scaffold `specs/chore-<name>/` and fill at least
`planning-spec.md` (what/why) + `deployment-spec.md`.

## MCP Integration
Prefer connected MCP servers (GitHub MCP + CodeRabbit always available).
- **Trackers:** link the maintenance ticket; post PR link.
- **Git hosting / CI:** open PR, poll checks, read failing logs.
- **Dependency/security-advisory MCP (if connected):** check advisories when bumping deps.
Only use connected servers; else `git` + GitHub MCP.

## Resuming
- **Branch cut from `railway`?** → skip step 1.
- **Change made, working tree dirty?** → resume at step 3 (verify).
- **Pushed with a PR open?** → resume at step 4 (pipeline check).

## Steps

1. **Create a chore branch**
   - `git fetch origin railway` → `git switch --create chore/<name> origin/railway`.
   - Scaffold `specs/chore-<name>/`; note the task in `planning-spec.md`; record baseline
     `pytest`.

2. **Make the change**
   - Apply the maintenance change (bump/config/cleanup) with minimal scope. No behavior
     change; no unrelated refactors. Note any new/changed env vars in
     `implementation-spec.md` and `.env.example`.

3. **Verify nothing broke**
   - Run `pytest tests/ -v` (+ `cd dashboard && npm run lint && npm run build` if the
     frontend/deps were touched). Everything must stay green.
   - **Loop-back:** the change broke something → fix here; if it's fundamentally
     incompatible, reconsider the change (or stop and ask the user). **Loop cap 3** → ask.

4. **Ship** (`chalk-ship` skill)
   - Invoke `chalk-ship`: `deployment-spec.md`, housekeeping (`TODO.md`/`CHANGELOG.md`),
     push, PR with **base = `railway`** (never `main`).
   - **Pipeline check (MCP):** on failure read logs → **step 2/3**. **Loop cap 3** → ask
     user. On pass, CodeRabbit triage.

5. **Compound (optional)** — usually skip for routine chores; run `chalk-compound` only
   if the task surfaced something worth remembering.
