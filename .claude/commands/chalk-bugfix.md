---
description: End-to-end bug-fix workflow — branch off railway, reproduce with a failing test, plan, fix, review, ship (PR into railway), and optionally compound. Loops back on failure.
argument-hint: "<short bug description or ticket key>"   (optional)
---

# chalk-bugfix

> Fix a bug from report to merged PR — reproduce first, then fix, in one self-correcting loop.

Branch off `railway`, never `main`. Produce the five specs in `specs/<branch-slug>/`.
The defining rule of this workflow: **no fix without a failing test that reproduces the
bug first.**

## MCP Integration

Use whatever MCP servers are connected; prefer MCP over manual paths. GitHub MCP
(`mcp__github__*`) and CodeRabbit are always available here.
- **Trackers:** pull the bug ticket for repro steps + expected behavior; move it across
  states; post the PR link.
- **Git hosting / CI:** open the PR, poll checks, read failing job logs.
- **Code quality:** check the gate after CI passes.
Only use connected servers; else fall back to `git` + GitHub MCP.

## Resuming
- **Branch cut from `railway`?** → skip step 1.
- **`planning-spec.md` (root-cause) filled?** → skip step 2.
- **Failing repro test written?** → resume at step 4 (fix).
- **Pushed with a PR open?** → resume at step 6 (pipeline check).

## Steps

1. **Create a bugfix branch**
   - Short name (e.g. `fix-null-usage-rate`); pull ticket context via MCP if referenced,
     move it to *In Progress*.
   - `git fetch origin railway` → `git switch --create bugfix/<name> origin/railway`.
   - Scaffold `specs/bugfix-<name>/` from `.claude/templates/`; record baseline
     `pytest` result.

2. **Diagnose the root cause** (`chalk-brainstorm` skill)
   - Invoke `chalk-brainstorm` to capture the observed vs expected behavior, repro
     steps, affected module, and the **root cause** (not just the symptom) →
     `planning-spec.md`. No code yet.

3. **Reproduce with a failing test + plan the fix** (`chalk-plan` skill)
   - First, write a test that **fails because of the bug** and confirm it fails for the
     right reason (record it in `testing-spec.md`).
   - Then invoke `chalk-plan` for the minimal fix design → `design-spec.md` +
     `implementation-spec.md` (API/DB/security as needed; often "no changes").

4. **Fix it** (`chalk-work` skill)
   - Invoke `chalk-work`: make the failing repro test pass with the smallest change,
     add regression tests, keep the whole suite green.
   - **Loop-back:** wrong root cause / plan → **step 2 or 3**. **Loop cap:** 3
     no-progress rounds → ask the user.

5. **Review** (`chalk-review` skill)
   - Invoke `chalk-review`. Blocking code issue → **step 4**; design flaw → **step 3**.
     Verify the `as_of_date` gate and idempotency weren't broken by the fix.

6. **Ship** (`chalk-ship` skill)
   - Invoke `chalk-ship`: `deployment-spec.md`, green gate, `TODO.md`/`CHANGELOG.md`,
     push, PR with **base = `railway`** (never `main`).
   - **Pipeline check (MCP):** on failure read logs → test/lint/build → **step 4**;
     design flaw → **step 3**. **Loop cap 3** → ask user. Re-commit + re-check after
     fixing. On pass, check the quality gate + run the CodeRabbit triage flow.

7. **Compound (optional)** (`chalk-compound` skill)
   - Ask whether to document the root cause + fix for future reference. If **yes**,
     invoke `chalk-compound`; else skip.
