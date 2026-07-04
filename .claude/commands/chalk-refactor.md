---
description: End-to-end refactor workflow — branch off railway, lock behavior with characterization tests, plan, refactor, review, ship (PR into railway), compound. Loops back on failure.
argument-hint: "<what you're refactoring>"   (optional)
---

# chalk-refactor

> Restructure code **without changing behavior** — proven by tests that stay green
> before and after.

Branch off `railway`, never `main`. Produce the five specs. The defining rule:
**behavior must not change** — characterization tests are green before you start and
identical after you finish.

## MCP Integration
Prefer connected MCP servers (GitHub MCP + CodeRabbit always available).
- **Trackers:** link the tech-debt ticket; move states; post PR link.
- **Git hosting / CI:** open PR, poll checks, read failing logs.
- **Code quality (SonarQube/CodeRabbit):** especially valuable here — compare
  complexity/duplication before vs after.
Only use connected servers; else `git` + GitHub MCP.

## Resuming
- **Branch cut from `railway`?** → skip step 1.
- **Characterization tests green + captured?** → resume at step 4.
- **Pushed with a PR open?** → resume at step 6 (pipeline check).

## Steps

1. **Create a refactor branch**
   - `git fetch origin railway` → `git switch --create refactor/<name> origin/railway`.
   - Scaffold `specs/refactor-<name>/`; record baseline `pytest` result.

2. **Scope + capture current behavior** (`chalk-brainstorm` skill)
   - Invoke `chalk-brainstorm`: what's being restructured and why, the exact behavioral
     contract that must be preserved, and explicit out-of-scope → `planning-spec.md`.
   - Ensure characterization tests exist and pass for the code in scope; add any that
     are missing (record in `testing-spec.md`). **These are your safety net.**

3. **Plan the restructure** (`chalk-plan` skill)
   - Invoke `chalk-plan` → `design-spec.md` + `implementation-spec.md`. Public
     interfaces and API/DB contracts should be unchanged (state so explicitly); the
     `as_of_date` gate stays intact on every touched feature function.

4. **Refactor** (`chalk-work` skill)
   - Invoke `chalk-work` in small steps; the characterization tests stay **green after
     every step**. No behavior change, no new features.
   - **Loop-back:** a green test goes red → you changed behavior; revert that step and
     rethink (or → **step 3** if the plan is flawed). **Loop cap 3** → ask the user.

5. **Review** (`chalk-review` skill)
   - Invoke `chalk-review`: confirm behavior is unchanged and the code is genuinely
     simpler. Blocking issue → **step 4**; design flaw → **step 3**.

6. **Ship** (`chalk-ship` skill)
   - Invoke `chalk-ship`: `deployment-spec.md`, green gate, housekeeping, push, PR with
     **base = `railway`** (never `main`).
   - **Pipeline check (MCP):** on failure read logs → **step 4** (or **step 3**). **Loop
     cap 3** → ask user. On pass, compare the quality gate to baseline, then CodeRabbit
     triage.

7. **Compound (optional)** (`chalk-compound` skill)
   - Ask whether to capture the pattern/anti-pattern learned. If **yes**, invoke
     `chalk-compound`; else skip.
