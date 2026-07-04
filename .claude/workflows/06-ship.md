# Workflow 06 — Ship

**Phase 6 of the Chalk Dev Flow.** Borrows from Superpowers
`finishing-a-development-branch`. Triggered by [`/chalk-ship`](../commands/chalk-ship.md).

The job of this phase: write the **deployment spec**, get the branch green and
pushed, and open a PR **into `railway`** (never `main`).

**Output:** `specs/<branch-slug>/deployment-spec.md`
(template: [`deployment-spec.md`](../templates/deployment-spec.md)) + a PR targeting
`railway`.

---

## Step 1 — Write the deployment spec

Fill the template. It must answer:

- **Target:** merges into **`railway`**. `main` is not a deploy target for feature
  work.
- **Migrations:** which Alembic revisions run, in what order; the rollback path.
- **Railway services affected:** `web`, `thepaint` (frontend), `ingest` cron (07:00
  UTC), `prediction` cron (18:00 UTC), `Redis`. Note if the shared Docker image or
  start commands change. Remember: Python services must use the `DOCKERFILE` builder,
  not Railpack.
- **Config / env:** any new env vars (added to `.env.example` **and** the Railway
  service), Redis URL via `${{Redis.REDIS_URL}}`, Supabase Session Pooler connection.
- **Model artifacts:** MLflow is not deployed in prod — any new model files are
  committed to git and loaded from disk. List them.
- **Rollout & verification:** how to confirm success post-merge (health check, a
  sample `/v1/...` call, cron log check) and the p99 < 500ms budget.
- **Rollback plan:** how to revert (branch revert + migration down-path).
- **Known follow-ups:** nits deferred from phase 5.

## Step 2 — Final green gate

```bash
pytest tests/ -v
cd dashboard && npm run lint && npm run build   # if the frontend was touched
```

All green, or the branch does not ship.

## Step 3 — Housekeeping (Chalk session rules)

- Update **`TODO.md`**: what changed and why, files modified, phase status, new/deferred
  issues.
- Add a dated **`CHANGELOG.md`** entry (`## YYYY-MM-DD` with `### Done / Metrics /
  Pending / Next`).
- Confirm the five specs in `specs/<branch-slug>/` reflect the final code.

## Step 4 — Push & open the PR

```bash
git push -u origin <prefix>/<slug>
```

Open the PR with **base = `railway`** (production rule: all changes target `railway`,
not `main`). Use the repo `.github/PULL_REQUEST_TEMPLATE.md` — mirror its headings and
fill them from the specs. Link the spec folder in the description.

> Do not open a PR into `main`. `main` only receives the deliberate `railway → main`
> release merge described in [`00-branch-naming.md`](00-branch-naming.md#appendix--the-railway--main-release-merge).

## Step 5 — PR review flow (CLAUDE.md mandatory)

1. Wait ~60s for CodeRabbit.
2. Fetch its review (`mcp__coderabbitai__get_coderabbit_reviews`).
3. Triage: fix actionable bugs/security/correctness; skip pure nits unless fast.
4. Commit & push fixes.
5. Re-fetch to confirm resolution.
6. Hand off with a summary of fixed vs. intentionally-skipped.

## Step 6 — Cleanup

Once merged: delete the branch, and remove the git worktree if one was used
(`git worktree remove ../chalk-<slug>`).

---

## Definition of done for phase 6

- [ ] `deployment-spec.md` complete (target, migrations, services, env, rollback)
- [ ] Full test suite green
- [ ] `TODO.md` and `CHANGELOG.md` updated
- [ ] Branch pushed; PR opened **into `railway`** using the PR template
- [ ] CodeRabbit review triaged and addressed

Next: [`/chalk-compound`](../commands/chalk-compound.md) →
[`07-compound.md`](07-compound.md).
