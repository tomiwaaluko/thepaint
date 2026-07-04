---
description: CI/CD pipeline workflow — branch off railway, change pipeline config, verify the pipeline itself runs green, ship (PR into railway). Loops back on failure.
argument-hint: "<what CI change>"   (optional)
---

# chalk-ci

> Change the CI/CD pipeline — and prove the pipeline itself still runs green — shipped
> through `railway`.

Branch off `railway`, never `main`. The tricky part: the change *is* the pipeline, so
verification means watching a real pipeline run via MCP. Scaffold `specs/ci-<name>/`;
fill `planning-spec.md`, `implementation-spec.md` (pipeline config + **security rules**:
no secrets in YAML, use masked CI variables), and `deployment-spec.md`.

## MCP Integration
Prefer connected MCP servers (GitHub MCP + CodeRabbit always available).
- **Git hosting / CI (GitHub Actions / GitLab):** this is the core dependency — trigger
  the pipeline, poll job status, read job logs to confirm the config change behaves.
- **Trackers:** link the ticket; post PR link.
Only use connected servers; else `git` + the GitHub MCP.

## Resuming
- **Branch cut from `railway`?** → skip step 1.
- **Config changed, working tree dirty?** → resume at step 3 (verify via a run).
- **Pushed with a PR open?** → resume at step 4 (pipeline check).

## Steps

1. **Create a ci branch**
   - `git fetch origin railway` → `git switch --create ci/<name> origin/railway`.
   - Scaffold `specs/ci-<name>/`.

2. **Change the pipeline config**
   - Edit the workflow/pipeline files. **Never hardcode secrets** — reference masked CI
     variables. Keep the change scoped; document each job's intent in
     `implementation-spec.md`.

3. **Verify the pipeline runs**
   - Push the branch early and use the Git-hosting MCP to trigger/observe a real
     pipeline run; read job logs to confirm each stage behaves as intended (not just
     "green by skipping").
   - **Loop-back:** a job fails or misbehaves → read the log, fix the config, re-run.
     **Loop cap 3** → ask the user.

4. **Ship** (`chalk-ship` skill)
   - Invoke `chalk-ship`: `deployment-spec.md` (note any change to how `web`/cron images
     build — Python services must keep the `DOCKERFILE` builder), housekeeping, PR with
     **base = `railway`** (never `main`).
   - **Pipeline check (MCP):** the pipeline *is* the deliverable here — it must be green
     on the PR. On failure → **step 2/3**. **Loop cap 3** → ask user. Then CodeRabbit
     triage.

5. **Compound (optional)** — run `chalk-compound` if a CI gotcha is worth recording.
