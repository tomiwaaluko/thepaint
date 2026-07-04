---
name: chalk-plan
description: Phase skill — turn a requirements-only planning spec into an implementation-ready design + implementation spec (API, DB, security). Invoked by the chalk-* branch workflows.
---

# chalk-plan

> Turn requirements into a buildable plan — the design and the implementation spec.

Reads `specs/<branch-slug>/planning-spec.md`. Produces two documents:
- `specs/<branch-slug>/design-spec.md` (template `.claude/templates/design-spec.md`)
- `specs/<branch-slug>/implementation-spec.md` (template
  `.claude/templates/implementation-spec.md`) — **including API, DB, and security specs**

## MCP (optional)
If a tracker MCP is connected, keep the linked ticket updated (e.g. move to *In
Progress* / *Planning*). For broad blast-radius mapping, dispatch a read-only `Plan`
or `Explore` subagent and fold its findings in.

## Part A — Design spec (the *shape*)
1. **Approach** — chosen architecture in prose (+ diagram if it helps); reference the
   module map in `CLAUDE.md`.
2. **Component breakdown** — real file paths, each with a single responsibility.
3. **Data flow** — trace one record/request end to end.
4. **Key decisions** — each with the rejected alternative and why. Honor the Chalk
   decisions: XGBoost over deep learning, one model per stat, Opportunity Score
   recomputed at predict time, 3× recency weighting.
5. **Interfaces** — signatures other modules call. **Every feature-generating function
   carries `as_of_date: datetime`.**

## Part B — Implementation spec (the *buildable plan*)
Break the work into bite-sized tasks (2–5 min each), each with exact file path,
change, and verification. Then complete the three mandatory sub-sections:

- **API spec** — routes (`/v1/{resource}/{id}/{action}`), method, params, request/
  response Pydantic schemas, status codes + error mapping (`IngestError` /
  `FeatureError` / `PredictionError` → HTTP), `async def` handlers, Redis caching
  (15-min TTL, injury-refresh invalidation), p99 < 500ms. Mark "No API changes" if none.
- **DB spec** — tables/columns touched, Alembic migration (up + down), indexes /
  TimescaleDB notes, and **idempotent upsert** (`INSERT … ON CONFLICT DO UPDATE`) with
  the conflict target. Mark "No DB changes" if none.
- **Security rules** — no secrets in code/tests/fixtures (config via
  `pydantic-settings`/`.env`); Pydantic-validated input + parameterized queries;
  CORS/`ALLOWED_ORIGINS`; list every function that must enforce the `as_of_date`
  gate; PII/least-privilege; pinned deps.

## Part C — Validation strategy
State it: walk-forward only (train 2015–2022, validate 2022–23, test 2023–24) — never
random k-fold.

## Done when
- [ ] `design-spec.md` complete (approach, components w/ real paths, data flow,
      decisions, interfaces all carrying `as_of_date`)
- [ ] `implementation-spec.md` broken into small verifiable tasks
- [ ] API / DB / security sub-sections filled (or explicitly "no changes")
- [ ] Both specs cross-check against `planning-spec.md` success criteria

## Report back
Summarize the plan and flag anything that suggests the requirements were wrong — the
calling workflow may loop back to `chalk-brainstorm`.
