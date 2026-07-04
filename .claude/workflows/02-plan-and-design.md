# Workflow 02 — Plan & Design

**Phase 2 of the Chalk Dev Flow.** Borrows from Compound Engineering `ce-plan` and
Superpowers `writing-plans`. Triggered by [`/chalk-plan`](../commands/chalk-plan.md).

The job of this phase: turn the requirements-only planning spec into an
**implementation-ready** design. This phase owns *two* spec documents.

**Outputs:**
- `specs/<branch-slug>/design-spec.md` — the shape of the solution
  (template: [`design-spec.md`](../templates/design-spec.md))
- `specs/<branch-slug>/implementation-spec.md` — the buildable plan, **including API
  spec, DB spec, and security rules**
  (template: [`implementation-spec.md`](../templates/implementation-spec.md))

---

## Part A — Design spec (the *shape*)

Answer "what will this look like" before "how do I build it".

1. **Approach** — the chosen architecture, in prose + a diagram if it helps.
   Reference the module map in `CLAUDE.md` ("Repo Structure").
2. **Component breakdown** — which files/modules change or get created, and each
   one's single responsibility. Real paths now (`chalk/features/opponent.py`, …).
3. **Data flow** — trace a request/record end to end (ingest → feature → model →
   prediction → api → dashboard, as applicable).
4. **Key design decisions** — each with the alternative rejected and why. Honor the
   Chalk decisions: XGBoost over deep learning, one model per stat, Opportunity Score
   recomputed at predict time, 3× recency weighting.
5. **Interfaces / contracts** — the function signatures and types other modules will
   call. Every feature-generating function **must** carry `as_of_date: datetime`.

## Part B — Implementation spec (the *buildable plan*)

Break the design into bite-sized tasks (2–5 minutes of work each, Superpowers style),
each with exact file paths, the change to make, and how to verify it. Then complete
the three mandatory sub-sections:

### B1 — API spec
For any FastAPI change:
- Route(s) following `/v1/{resource}/{id}/{action}` (e.g. `/v1/players/2544/predict`)
- Method, path params, query params, request body schema, response schema (Pydantic)
- Status codes and error responses (`IngestError`/`FeatureError`/`PredictionError`
  → HTTP mapping)
- `async def` handlers only; Redis caching behavior (15-min TTL, injury-refresh
  invalidation) and the p99 < 500ms budget
- If no API surface changes, state "No API changes" explicitly.

### B2 — DB spec
For any data-layer change:
- Tables touched (see `CLAUDE.md` → "Database Schema") and new columns/types
- Alembic migration plan (`alembic/versions/…`) — up and down
- Indexes / TimescaleDB hypertable considerations
- **Idempotency:** all writes use `INSERT … ON CONFLICT DO UPDATE` (upsert), never
  plain `INSERT`. State the conflict target.
- If no schema changes, state "No DB changes" explicitly.

### B3 — Security rules
Always complete this section:
- **Secrets:** no keys/tokens in code, tests, or fixtures; config via
  `pydantic-settings` / `.env` only
- **Input validation:** Pydantic models validate all external input; parameterized
  queries only (no string-built SQL)
- **CORS / origins:** validate `ALLOWED_ORIGINS` if touching API startup
- **Data-leakage-as-security:** the `as_of_date` gate is a correctness *and*
  integrity control — call out every function that must enforce it
- **Least privilege / PII:** note any player PII handling and access scope
- **Dependencies:** new deps pinned; no unvetted packages

## Part C — Validation strategy stub

Note the intended validation approach so phase 3 can pick it up:
time-series **walk-forward only** (train 2015–2022, validate 2022–23, test 2023–24) —
**never** random k-fold on sports data.

---

## Subagents

For a larger change, dispatch a read-only `Plan` or `Explore` subagent to map the
blast radius and surface hidden coupling, then fold its findings into the specs. Keep
the decision-making in the main thread.

## Definition of done for phase 2

- [ ] `design-spec.md` complete with approach, components (real paths), data flow,
      decisions, interfaces (all feature fns carry `as_of_date`)
- [ ] `implementation-spec.md` broken into small verifiable tasks
- [ ] API spec, DB spec, and security-rules sub-sections all filled (or explicitly
      marked "no changes")
- [ ] Idempotent-upsert and walk-forward-validation rules honored on paper
- [ ] Both specs cross-check against the `planning-spec.md` success criteria

Next: [`/chalk-test`](../commands/chalk-test.md) → [`03-test.md`](03-test.md).
