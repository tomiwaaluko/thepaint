---
name: chalk-ship
description: Phase skill — write the deployment spec, pass the green gate, push, open a PR into railway (never main), and drive CI/quality gates green via MCP. Invoked by the chalk-* branch workflows.
---

# chalk-ship

> Get green, push, and open a PR **into `railway`** — then drive CI to green.

Produces `specs/<branch-slug>/deployment-spec.md` (template
`.claude/templates/deployment-spec.md`) and a PR targeting `railway`.

## MCP (use what's connected)
- **Git hosting** (GitHub / GitLab MCP): open the PR/MR, poll pipeline/checks status,
  read failing job logs. The GitHub MCP (`mcp__github__*`) is available in this session.
- **Tracker** (Jira / Linear / …): post the PR link on the ticket, move it to *In
  Review*.
- **Code quality** (SonarQube / CodeRabbit): after CI passes, check the quality gate /
  automated review.
- Only use servers that are actually connected; otherwise fall back to `git` + the
  GitHub MCP.

## Steps
1. **Deployment spec** — fill the template: target = **`railway`**; Alembic migrations
   (up + down); Railway services affected (`web`, `thepaint`, `ingest` cron 07:00 UTC,
   `prediction` cron 18:00 UTC, `Redis`; Python services use the `DOCKERFILE` builder);
   new env vars (added to `.env.example` **and** the Railway service); model artifacts
   (committed to git — MLflow is not deployed in prod); rollout/verification (health,
   sample `/v1/...`, cron logs, p99 < 500ms); rollback plan; known follow-ups.
2. **Green gate** — `pytest tests/ -v` (+ `npm run lint && npm run build` if the
   frontend was touched). All green or it does not ship.
3. **Housekeeping** — update `TODO.md` and add a dated `CHANGELOG.md` entry
   (`### Done / Metrics / Pending / Next`). Confirm the five specs match the code.
4. **Push & PR** — `git push -u origin <prefix>/<slug>`; open the PR with **base =
   `railway`** using `.github/PULL_REQUEST_TEMPLATE.md`. **Never open a PR into `main`.**
5. **CI / pipeline check (MCP)** — poll the pipeline until it settles. If it **fails**,
   read the failing job log and report the diagnosis back to the calling workflow so it
   can loop to the right phase (test/lint/build → `chalk-work`; design flaw →
   `chalk-plan`). After CI passes, check the code-quality gate; treat a gate failure
   like a CI failure.
6. **CodeRabbit flow (CLAUDE.md, mandatory)** — wait ~60s, fetch the review, triage and
   fix actionable items, push, re-fetch to confirm, hand off with a fixed-vs-skipped
   summary.

## `main` is off-limits
`main` only changes via the deliberate `railway → main` release merge (see the
`chalk-release` path / README). Never as a side effect of feature work.

## Done when
- [ ] `deployment-spec.md` complete; full suite green; `TODO.md` + `CHANGELOG.md` updated
- [ ] Branch pushed; PR opened **into `railway`** via the template
- [ ] CI/pipeline green (looped back on failure); quality gate green; CodeRabbit triaged
