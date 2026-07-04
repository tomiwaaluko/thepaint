---
description: Formatting / UI-styling workflow — branch off railway, apply style-only changes, verify lint + build with no behavior change, ship (PR into railway). Loops back on failure.
argument-hint: "<what styling>"   (optional)
---

# chalk-style

> Formatting and UI-styling only — **zero behavior change** — verified and shipped
> through `railway`.

Branch off `railway`, never `main`. Lightest loop. Scaffold `specs/style-<name>/`; fill
`planning-spec.md` + `deployment-spec.md`. The defining rule: **no logic changes** — if
you need to change behavior, that's a different prefix.

## MCP Integration
Prefer connected MCP servers (GitHub MCP + CodeRabbit always available).
- **Trackers:** link the ticket; post PR link.
- **Git hosting / CI:** open PR, poll lint/build jobs, read failing logs.
- **Design MCP (Figma, if connected):** pull the target spacing/tokens for UI styling.
Only use connected servers; else `git` + GitHub MCP.

## Resuming
- **Branch cut from `railway`?** → skip step 1.
- **Changes made, working tree dirty?** → resume at step 3 (verify).
- **Pushed with a PR open?** → resume at step 4 (pipeline check).

## Steps

1. **Create a style branch**
   - `git fetch origin railway` → `git switch --create style/<name> origin/railway`.
   - Scaffold `specs/style-<name>/`; note scope in `planning-spec.md`.

2. **Apply the style change**
   - Formatting (Python PEP 8 / ESLint-Prettier) or UI styling only. Do not touch logic,
     signatures, or the `as_of_date` gate. For UI, attach before/after screenshots for
     the PR.

3. **Verify (no behavior change)**
   - Backend: `pytest tests/ -v` stays green. Frontend: `npm run lint && npm run build`.
     The test suite must be **identical** in outcome to baseline.
   - **Loop-back:** a test changed outcome → you changed behavior; revert that part.
     **Loop cap 3** → ask the user.

4. **Ship** (`chalk-ship` skill)
   - Invoke `chalk-ship`: `deployment-spec.md`, housekeeping, push, PR with **base =
     `railway`** (never `main`); include UI screenshots.
   - **Pipeline check (MCP):** on failure read logs → **step 2/3**. **Loop cap 3** → ask
     user. On pass, CodeRabbit triage.

5. **Compound (optional)** — normally skip.
