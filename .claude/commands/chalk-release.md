---
description: Release workflow — branch off railway, prep the release (version + changelog), verify, then perform the deliberate railway→main promotion. The ONLY workflow that touches main. Loops back on failure.
argument-hint: "<version, e.g. v1.2.0>"   (optional)
---

# chalk-release

> Cut a release: prep on a `release/` branch off `railway`, then deliberately promote
> `railway → main`.

This is the **only** workflow allowed to touch `main`, and it does so on purpose, at the
end, with explicit user confirmation. Everything up to the promotion still branches off
`railway`. Scaffold `specs/release-<version>/`; fill `planning-spec.md` (scope of the
release) + `deployment-spec.md` (the promotion + rollback plan).

## MCP Integration
Prefer connected MCP servers (GitHub MCP + CodeRabbit always available).
- **Git hosting:** open the release PR, poll checks, create the tag/GitHub release.
- **Trackers:** compile the ticket list going out; move them to *Done/Released*; post
  release notes.
- **Deploy/monitoring MCP (if connected):** confirm services healthy post-promotion.
Only use connected servers; else `git` + GitHub MCP.

## Resuming
- **`release/<version>` branch cut from `railway`?** → skip step 1.
- **Version + changelog bumped?** → resume at step 3 (verify).
- **Release PR into `railway` merged?** → resume at step 5 (railway→main promotion).

## Steps

1. **Create a release branch**
   - Confirm the version (e.g. `v1.2.0`). `git fetch origin railway` →
     `git switch --create release/<version> origin/railway`.
   - Scaffold `specs/release-<version>/`.

2. **Prep the release**
   - Bump the version, finalize the dated `CHANGELOG.md` entry (roll up what's shipping),
     update `TODO.md`. Compile the change/ticket list. **No new features** — release prep
     only; if something needs fixing, branch a `bugfix/` off `railway` first.

3. **Verify the release candidate**
   - Full green gate: `pytest tests/ -v`, and `cd dashboard && npm run lint && npm run
     build`. Smoke-check a sample `/v1/...` path and the p99 budget.
   - **Loop-back:** anything red → the release is not ready; fix via the appropriate
     workflow (`bugfix`/`chore`) off `railway`, then return here. **Loop cap 3** → ask
     the user.

4. **Ship the release branch → `railway`** (`chalk-ship` skill)
   - Invoke `chalk-ship`: push `release/<version>`, open a PR with **base = `railway`**,
     drive the pipeline green (loop-back on failure as usual), run CodeRabbit triage, and
     merge into `railway`. Tag the release if that's the convention.

5. **Promote `railway → main` (deliberate, confirmed)**
   - **Confirm with the user first:** *"Ready to promote `railway` to `main` for
     `<version>`?"* Do not proceed without an explicit yes.
   - Then:
     ```bash
     git fetch origin
     git switch main && git pull origin main
     git merge --no-ff origin/railway     # bring railway's tested state into main
     git push origin main
     ```
   - Create the tag / GitHub release on `main` via MCP. Confirm services are healthy.
   - **Rollback:** if the promotion goes wrong, revert the merge on `main` and redeploy
     the previous tag (record this in `deployment-spec.md`).

6. **Compound (recommended)** (`chalk-compound` skill)
   - Invoke `chalk-compound` to capture release notes / process learnings for the next
     release in `docs/solutions/`.
