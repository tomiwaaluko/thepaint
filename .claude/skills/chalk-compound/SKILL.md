---
name: chalk-compound
description: Phase skill — capture the loop's learnings into docs/solutions so the next loop starts smarter. Invoked (optionally) at the end of the chalk-* branch workflows.
---

# chalk-compound

> Capture what this loop taught you so the next one starts smarter — the return arrow.

Produces a learning entry in `docs/solutions/` (created if absent).

## MCP (optional)
If a tracker MCP is connected, pull the closed ticket's discussion for extra context,
and/or post a short "lessons learned" note back on the ticket.

## Steps
1. **Harvest** — review this branch's five specs and the PR/review discussion. Extract:
   what surprised you (a wrong assumption, an nba_api quirk, a playoff-mode edge case, a
   leakage trap nearly hit); what worked (a pattern worth repeating); what to change
   next time.
2. **Write** `docs/solutions/<YYYY-MM-DD>-<branch-slug>.md`:
   - **Context** — what this branch set out to do.
   - **What we learned** — bullets.
   - **Reusable patterns** — link the file/function that embodies each.
   - **Traps & gotchas** — especially leakage / idempotency.
   - **Guidance for the next loop** — what a future `chalk-brainstorm`/`chalk-plan`
     should know before touching this area.
3. **Promote durable learnings** as small, separately-scoped follow-ups (their own
   `docs/` or `chore/` branch), not smuggled into the feature PR:
   - a recurring domain rule → propose an addition to `CLAUDE.md`
   - a reusable module technique → the relevant `.agents/skills/*/SKILL.md`
   - a repeated review miss → the `chalk-review` checklist
4. **Close the loop** — confirm `CHANGELOG.md` + `TODO.md` are final.

## Done when
- [ ] `docs/solutions/<date>-<slug>.md` written (learnings, patterns, traps, next-loop
      guidance)
- [ ] Durable learnings promoted where warranted (as separate follow-ups)
- [ ] Loop closed — ready to start the next branch workflow
