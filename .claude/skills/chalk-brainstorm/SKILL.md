---
name: chalk-brainstorm
description: Phase skill — turn a rough idea into a requirements-only planning spec (what/why, no code). Invoked by the chalk-* branch workflows; can also be run standalone.
---

# chalk-brainstorm

> Collaboratively define **requirements** — the *what* and *why*, never the *how*.

Produces `specs/<branch-slug>/planning-spec.md`
(template: `.claude/templates/planning-spec.md`).

## MCP (optional)
If an issue-tracker MCP is connected (Jira, Linear, GitHub Issues, …), and the user
referenced a ticket, pull its summary/description to seed the problem statement and
success criteria. Only use a tracker that is actually connected.

## Guard rails
- **Requirements only.** No file paths, functions, tables, or code — that is
  `chalk-plan`'s job. If you catch yourself designing, capture the requirement instead.
- **Focused questions.** Ask 2–4 sharp questions (use `AskUserQuestion` for genuine
  forks); pick sensible defaults for the rest and note them.
- **Surface the non-negotiables** from `CLAUDE.md` early as constraints: the
  `as_of_date` leakage rule, idempotent ingestion, async-all-the-way, time-series
  (walk-forward) validation only, one model per stat.

## Steps
1. **Frame** — write the problem statement, affected module(s) (ingestion / features /
   models / predictions / betting / fantasy / api / dashboard), and why now.
2. **Interrogate** — success criteria (tie to Chalk key numbers: PTS MAE ≤ 5.0, REB ≤
   2.5, AST ≤ 2.0, 3PM ≤ 1.2, Team Total ≤ 8.0, API p99 < 500ms), scope boundaries
   (what's explicitly out), constraints, risks/unknowns, and ≥1 rejected alternative.
3. **Ground lightly** — read enough of the codebase to keep requirements realistic
   (an `Explore` subagent is good for broad sweeps). Do **not** design the solution.
4. **Write** `planning-spec.md` — fill every section of the template.

## Done when
- [ ] `planning-spec.md` complete: problem, modules, success criteria, scope,
      constraints, risks, alternatives
- [ ] Zero implementation detail
- [ ] Relevant `CLAUDE.md` non-negotiables captured as constraints

## Report back
End with a 3–5 line summary and the path to the spec, so the calling workflow can
present the off-ramp ("continue to planning, or stop here?").
