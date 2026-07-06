---
description: End-to-end feature workflow — branch off railway, brainstorm, plan, work (TDD), review, ship (PR into railway), and optionally compound. Loops back on failure.
argument-hint: "<short feature name>"   (optional; you'll be asked if omitted)
---

# chalk-feature

> Add a new feature from idea to merged PR in one guided, self-correcting loop.

This is an **agentic loop workflow**: run it once and it drives every phase to done,
looping back to an earlier phase whenever a later one fails. Honor the golden rule —
**branch off `railway`, never touch `main`** — and produce the five specs in
`specs/<branch-slug>/` as you go.

## MCP Integration

Use whatever MCP servers are currently connected to this session. Before any step that
touches an external system, check what's available (search tools) and prefer the MCP
tool over a manual path. This session always has the **GitHub MCP** (`mcp__github__*`)
and **CodeRabbit** for reviews.

- **Issue/ticket trackers** (Jira, Linear, GitHub Issues, …): if a ticket is
  referenced, pull its details for the branch name + requirements, and move it across
  states (*In Progress* → *In Review*) as you progress.
- **Git hosting / CI** (GitHub, GitLab): open the PR, poll pipeline/checks status, read
  failing job logs.
- **Code quality** (SonarQube, CodeRabbit): check the quality gate / review after CI
  passes.
- Only use servers that are actually connected; if none fits a step, fall back to
  `git` + the GitHub MCP.

## Resuming

If this workflow was interrupted, check what already exists before restarting:
- **Branch already cut from `railway`?** → skip step 1.
- **`specs/<slug>/planning-spec.md` filled?** → skip step 2; feed it into step 3.
- **`design-spec.md` + `implementation-spec.md` filled?** → skip step 3; feed into step 4.
- **Tests written / working tree dirty?** → resume at step 4.
- **Pushed with a PR open?** → resume at step 6 (pipeline check).

## Steps

1. **Create a feature branch**
   - Ask the user for a short feature name (e.g. `opponent-usage-rate`) if not provided.
   - If a ticket key was given and a tracker MCP is connected, pull its summary and
     use it in the name; move the ticket to *In Progress*.
   - `git fetch origin railway` then `git switch --create feature/<name> origin/railway`.
     **Base must be `railway`, never `main`.**
   - Scaffold `specs/feature-<name>/` by copying the five files from
     `.claude/templates/`. Record the baseline `pytest tests/ -v` result in the
     planning spec.

2. **Brainstorm the feature** (`chalk-brainstorm` skill)
   - Invoke the `chalk-brainstorm` skill to define requirements → `planning-spec.md`.
   - **Off-ramp:** ask the user *"Requirements are defined. Continue to planning, or
     stop here?"* If **stop**, end the workflow.

3. **Plan the implementation** (`chalk-plan` skill)
   - Invoke `chalk-plan`, feeding it the planning spec. Produces `design-spec.md` and
     `implementation-spec.md` (API + DB + security).

4. **Work the plan test-first** (`chalk-work` skill)
   - Invoke `chalk-work`: RED → GREEN → simplify, one task at a time; produces
     `testing-spec.md` and passing code.
   - **Loop-back:** if `chalk-work` reports the *plan itself* is wrong → go back to
     **step 3**. Otherwise fix within step 4.
   - **Loop cap:** if the same task fails to progress after **3 rounds**, stop and ask
     the user instead of looping again.
   - All tests must pass before proceeding.

5. **Review** (`chalk-review` skill)
   - Invoke `chalk-review`: simplify + review against specs and non-negotiables.
   - **Loop-back:** code-level blocking finding → **step 4**; design-level flaw →
     **step 3**. Re-review after fixes. Proceed only when no blocking findings remain.

6. **Ship** (`chalk-ship` skill)
   - Invoke `chalk-ship`: write `deployment-spec.md`, pass the green gate, update
     `TODO.md` + `CHANGELOG.md`, push, and open the PR with **base = `railway`** (never
     `main`). Post the PR link on the ticket via MCP if connected.
   - **Pipeline check (MCP):** poll the pipeline/checks until settled. If it **fails**,
     read the failing job log and diagnose:
     - test / lint / build failure → **loop back to step 4** (`chalk-work`)
     - fundamental design issue → **loop back to step 3** (`chalk-plan`)
     - **Loop cap:** if this pipeline→fix loop has already run **3 times**, stop and ask
       the user. After fixing, re-commit and re-check the pipeline.
   - When the pipeline **passes**, check the code-quality gate (e.g. SonarQube/
     CodeRabbit); a gate failure is treated like a pipeline failure. Then run the
     mandatory CodeRabbit triage flow.

7. **Compound (optional)** (`chalk-compound` skill)
   - Ask the user *"Would you like to run `chalk-compound` to document this solution for
     future reference?"* If **yes**, invoke `chalk-compound`; if **no**, skip.
