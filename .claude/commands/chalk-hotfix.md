---
description: Fast-tracked urgent production fix — branch off railway, reproduce with a failing test, fix, focused review, expedited ship (PR into railway), compound. Loops back on failure.
argument-hint: "<short incident description>"   (optional)
---

# chalk-hotfix

> Urgent production fix, fast — minimal ceremony, but still reproduced, tested, and
> shipped through `railway`.

This is the fast lane. It compresses brainstorm/plan into a one-paragraph justification,
but it does **not** skip: branching off `railway`, a failing repro test, review, and a
PR into `railway`. **`main` is never touched directly**, even under incident pressure.

## MCP Integration
Prefer connected MCP servers. GitHub MCP + CodeRabbit are always available.
- **Trackers:** link the incident ticket; move to *In Progress* → *In Review*; post PR link.
- **Git hosting / CI:** open the PR, poll checks, read failing logs fast.
- **Monitoring/alerting MCP (if connected):** confirm the incident signal and, post-fix,
  confirm recovery.
Only use connected servers; else `git` + GitHub MCP.

## Resuming
- **Branch cut from `railway`?** → skip step 1.
- **Failing repro test written?** → resume at step 3 (fix).
- **Pushed with a PR open?** → resume at step 5 (pipeline check).

## Steps

1. **Create a hotfix branch**
   - `git fetch origin railway` → `git switch --create hotfix/<name> origin/railway`.
   - Scaffold `specs/hotfix-<name>/`. In `planning-spec.md`, write a **one-paragraph**
     incident summary: impact, blast radius, and the minimal fix intent (full brainstorm
     is skipped — this is urgent).

2. **Reproduce with a failing test**
   - Write the smallest test that fails because of the production bug; confirm it fails
     for the right reason. Record it in `testing-spec.md`. Note the minimal design in
     `design-spec.md` / `implementation-spec.md` (usually "no API/DB changes").

3. **Fix it** (`chalk-work` skill)
   - Invoke `chalk-work`: smallest change to make the repro test pass; keep the suite
     green; do not expand scope. **Loop-back:** if the diagnosis was wrong → back to
     step 2. **Loop cap 3** → escalate to the user immediately (it's an incident).

4. **Focused review** (`chalk-review` skill)
   - Invoke `chalk-review` scoped to correctness + the non-negotiables (`as_of_date`,
     idempotency, async). Blocking issue → **step 3**.

5. **Expedited ship** (`chalk-ship` skill)
   - Invoke `chalk-ship`: `deployment-spec.md` (call out the rollback plan explicitly),
     green gate, `TODO.md`/`CHANGELOG.md`, push, PR with **base = `railway`**.
   - **Pipeline check (MCP):** on failure read logs → **step 3**. **Loop cap 3** → ask
     the user. On pass, run the CodeRabbit triage flow (don't skip it even under
     pressure), then flag the PR for urgent human merge.

6. **Compound** (`chalk-compound` skill)
   - For incidents, default to running it: invoke `chalk-compound` to write a short
     post-incident note (root cause, why it reached prod, prevention) in
     `docs/solutions/`. Ask only if the user wants to skip.
