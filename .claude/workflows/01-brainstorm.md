# Workflow 01 — Brainstorm

**Phase 1 of the Chalk Dev Flow.** Borrows from Compound Engineering `ce-brainstorm`
and Superpowers `brainstorming`. Triggered by
[`/chalk-brainstorm`](../commands/chalk-brainstorm.md).

The job of this phase: turn a rough idea into a **requirements-only** planning spec —
*what* and *why*, never *how*. No file paths, no code, no schema yet. Those belong to
phase 2.

**Output:** `specs/<branch-slug>/planning-spec.md`
(template: [`planning-spec.md`](../templates/planning-spec.md))

---

## Guard rails

- **Requirements only.** If you catch yourself naming a function or a table column,
  stop — that is phase 2's job. Capture the *requirement* it satisfies instead.
- **One decision at a time.** Ask focused questions; do not dump a 20-question
  survey. Prefer 2–4 sharp questions with a recommended default.
- **Respect the domain rules.** Any feature touching the model pipeline inherits the
  non-negotiables from `CLAUDE.md`: the `as_of_date` leakage rule, idempotent
  ingestion, async-all-the-way, time-series validation only, one model per stat.
  Surface these as constraints early.

## Step 1 — Frame the problem

Write, in `planning-spec.md`:

- **Problem statement** — what hurts today, in one paragraph.
- **Who / what is affected** — which module(s): ingestion, features, models,
  predictions, betting, fantasy, api, dashboard.
- **Why now** — the trigger for doing this.

## Step 2 — Interrogate the idea

Work through these with the user (use `AskUserQuestion` for genuine forks; pick sane
defaults for the rest and note them):

1. **Success criteria** — how will we know this worked? Tie to Chalk's key numbers
   where relevant (PTS MAE ≤ 5.0, REB ≤ 2.5, AST ≤ 2.0, 3PM ≤ 1.2, Team Total ≤ 8.0,
   API p99 < 500ms).
2. **Scope boundaries** — what is explicitly *out* of scope for this branch.
3. **Constraints** — domain rules, latency budgets, data availability, playoff-mode
   quirks (playoff game-id prefix `004`, irregular schedules).
4. **Risks & unknowns** — what could make this fail or leak data.
5. **Alternatives considered** — at least one other approach and why it lost.

## Step 3 — Explore the codebase (light touch)

Read enough to ground the requirements in reality — where the affected module lives,
what already exists — but do **not** design the solution. If exploration is broad, a
read-only `Explore` subagent is a good fit here.

## Step 4 — Write the planning spec

Fill every section of the template. The spec is done when a second engineer could
read it and independently produce a design without asking you what the feature is
for.

---

## Definition of done for phase 1

- [ ] `planning-spec.md` complete: problem, affected modules, success criteria,
      scope, constraints, risks, alternatives
- [ ] Zero implementation detail (no code, no file paths, no columns)
- [ ] Relevant `CLAUDE.md` non-negotiables listed as constraints
- [ ] Baseline result from phase 0 still recorded

Next: [`/chalk-plan`](../commands/chalk-plan.md) →
[`02-plan-and-design.md`](02-plan-and-design.md).
