# Workflow 07 — Compound

**Phase 7 of the Chalk Dev Flow.** Borrows from Compound Engineering `ce-compound`.
Triggered by [`/chalk-compound`](../commands/chalk-compound.md).

The job of this phase: capture what this loop taught you so the *next* loop starts
smarter. This is the return arrow that makes the whole cycle compound.

**Output:** a learning entry in `docs/solutions/` (created if absent).

---

## Why bother

Compound Engineering's core claim: each cycle should make the next one cheaper. A
brainstorm informed by last week's gotcha is a better brainstorm; a plan that knows
which approach already failed is a better plan. Undocumented learnings evaporate.

## Step 1 — Harvest the learnings

Review this branch's five specs and the PR discussion, and extract:

- **What surprised you** — a design assumption that proved wrong, an nba_api quirk, a
  playoff-mode edge case, a leakage trap you nearly hit.
- **What worked** — a pattern worth repeating (a clean feature-pipeline shape, a
  useful test fixture, a good mock).
- **What to change next time** — process or code guidance for future branches.

## Step 2 — Write the solution doc

Create `docs/solutions/<YYYY-MM-DD>-<branch-slug>.md`:

```markdown
# <Title> — <branch-slug>

**Date:** YYYY-MM-DD  ·  **Branch:** <prefix>/<slug>  ·  **PR:** #NNN

## Context
One paragraph: what this branch set out to do.

## What we learned
- bullet ...

## Reusable patterns
- bullet ... (link to the file/function that embodies it)

## Traps & gotchas
- bullet ... (especially anything leakage- or idempotency-related)

## Guidance for the next loop
- What a future /chalk-brainstorm or /chalk-plan should know before touching this area.
```

## Step 3 — Promote durable learnings

If a learning is broad enough to apply to *all* future work, promote it beyond the
one-off doc:

- A recurring domain rule → propose an addition to `CLAUDE.md`.
- A reusable module technique → propose an update to the relevant
  `.agents/skills/*/SKILL.md`.
- A repeated review miss → add it to the phase-5 review checklist.

Do these as small, clearly-scoped follow-up changes (their own `docs/` or `chore/`
branch), not smuggled into the feature PR.

## Step 4 — Close the loop

Confirm `CHANGELOG.md` and `TODO.md` reflect the finished work, then the branch is
truly done. The next `/chalk-brainstorm` should read the freshest `docs/solutions/`
entries as grounding.

---

## Definition of done for phase 7

- [ ] `docs/solutions/<date>-<slug>.md` written with learnings, patterns, traps,
      next-loop guidance
- [ ] Durable learnings promoted to `CLAUDE.md` / a skill / the review checklist
      where warranted (as separate follow-ups)
- [ ] `CHANGELOG.md` + `TODO.md` final
- [ ] Loop closed — ready to `/chalk-branch` the next piece of work
