---
description: Documentation workflow — branch off railway, write/update docs, verify they build and links resolve, ship (PR into railway). Loops back on failure.
argument-hint: "<what docs>"   (optional)
---

# chalk-docs

> Documentation only — accurate, building, and shipped through `railway`.

Branch off `railway`, never `main`. Lightest loop: no code tests, but docs must build
and match reality. Scaffold `specs/docs-<name>/` and fill `planning-spec.md` +
`deployment-spec.md` (the rest are typically "N/A — docs only").

## MCP Integration
Prefer connected MCP servers (GitHub MCP + CodeRabbit always available).
- **Trackers:** link the docs ticket; post PR link.
- **Git hosting / CI:** open PR, poll the docs-build/link-check job, read failing logs.
- **Knowledge-base MCP (Notion/Confluence, if connected):** mirror or source content.
Only use connected servers; else `git` + GitHub MCP.

## Resuming
- **Branch cut from `railway`?** → skip step 1.
- **Docs written, working tree dirty?** → resume at step 3 (verify).
- **Pushed with a PR open?** → resume at step 4 (pipeline check).

## Steps

1. **Create a docs branch**
   - `git fetch origin railway` → `git switch --create docs/<name> origin/railway`.
   - Scaffold `specs/docs-<name>/`; note scope in `planning-spec.md`.

2. **Write / update the docs**
   - Make the change. **Verify claims against the actual code** — a doc that contradicts
     the code is a bug in the doc. If you find the code, not the doc, is wrong, stop and
     surface it (that's a `bugfix`, not a docs change).

3. **Verify**
   - Build the docs if there's a build step; check that internal links/anchors resolve
     and code snippets are current. If touching README/site, confirm it renders.
   - **Loop-back:** broken build/links → fix here. **Loop cap 3** → ask the user.

4. **Ship** (`chalk-ship` skill)
   - Invoke `chalk-ship`: `deployment-spec.md` (usually "docs only, no service impact"),
     housekeeping, push, PR with **base = `railway`** (never `main`).
   - **Pipeline check (MCP):** on failure read logs → **step 2/3**. **Loop cap 3** → ask
     user. On pass, CodeRabbit triage.

5. **Compound (optional)** — skip unless the docs work revealed a reusable insight.
