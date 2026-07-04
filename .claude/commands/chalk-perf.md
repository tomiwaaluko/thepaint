---
description: End-to-end performance workflow — branch off railway, capture a baseline metric, plan, optimize, prove the win with no regression, review, ship (PR into railway), compound. Loops back on failure.
argument-hint: "<what you're optimizing>"   (optional)
---

# chalk-perf

> Make it faster **and prove it** — a measured baseline, a measured improvement, and no
> behavior or accuracy regression.

Branch off `railway`, never `main`. Produce the five specs. The defining rule: **no
optimization is accepted without a before/after measurement.**

## MCP Integration
Prefer connected MCP servers (GitHub MCP + CodeRabbit always available).
- **Trackers:** link the perf ticket; move states; post PR link with the numbers.
- **Git hosting / CI:** open PR, poll checks, read failing logs.
- **APM / metrics / DB MCP (if connected):** capture latency/query timings for the
  baseline and the after-measurement.
Only use connected servers; else `git` + GitHub MCP.

## Resuming
- **Branch cut from `railway`?** → skip step 1.
- **Baseline metric captured in `planning-spec.md`?** → skip to step 3/4.
- **Pushed with a PR open?** → resume at step 6 (pipeline check).

## Steps

1. **Create a perf branch**
   - `git fetch origin railway` → `git switch --create perf/<name> origin/railway`.
   - Scaffold `specs/perf-<name>/`; record baseline `pytest` result.

2. **Measure the baseline + set the target** (`chalk-brainstorm` skill)
   - Invoke `chalk-brainstorm`: define the metric (e.g. p99 latency, query time,
     training time), **measure it now**, and set the target (respect the p99 < 500ms
     budget). Record baseline numbers in `planning-spec.md`. Model accuracy must not
     regress (PTS MAE ≤ 5.0, etc.).

3. **Plan the optimization** (`chalk-plan` skill)
   - Invoke `chalk-plan` → `design-spec.md` + `implementation-spec.md`. Add a perf
     assertion/benchmark to the test plan (`testing-spec.md`) so the win is enforced.

4. **Optimize** (`chalk-work` skill)
   - Invoke `chalk-work`: functional tests stay green; the perf test now passes.
     Preserve the `as_of_date` gate, idempotency, and accuracy.
   - **Loop-back:** approach doesn't move the metric → **step 3**. **Loop cap 3** → ask
     the user.

5. **Review + re-measure** (`chalk-review` skill)
   - Invoke `chalk-review`, and record the **after** measurement vs baseline. Blocking
     issue or accuracy regression → **step 4**; wrong strategy → **step 3**.

6. **Ship** (`chalk-ship` skill)
   - Invoke `chalk-ship`: `deployment-spec.md` (include before/after numbers), green
     gate, housekeeping, push, PR with **base = `railway`** (never `main`).
   - **Pipeline check (MCP):** on failure read logs → **step 4/3**. **Loop cap 3** → ask
     user. On pass, quality gate + CodeRabbit triage.

7. **Compound (optional)** (`chalk-compound` skill)
   - Ask whether to capture the optimization technique + numbers. If **yes**, invoke
     `chalk-compound`; else skip.
