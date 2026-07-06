# Planning Spec — <feature title>

> Requirements only. No file paths, no code, no schema — those live in the design and
> implementation specs. Owned by phase 1 (`/chalk-brainstorm`).

| | |
|---|---|
| **Branch** | `<prefix>/<slug>` |
| **Prefix rationale** | why this prefix |
| **Base** | `railway` |
| **Date** | YYYY-MM-DD |
| **Author** | |

## Baseline
- `pytest tests/ -v` result at branch start: PASS / FAIL (n passed, m failed)
- Frontend (if touched) `npm run build` / `lint`: PASS / FAIL / N/A

## Problem statement
What hurts today, in one paragraph.

## Affected modules
Which of: ingestion · features · models · predictions · betting · fantasy · api ·
dashboard.

## Why now
The trigger for doing this.

## Success criteria
How we'll know it worked. Tie to key numbers where relevant (PTS MAE ≤ 5.0, REB ≤
2.5, AST ≤ 2.0, 3PM ≤ 1.2, Team Total ≤ 8.0, API p99 < 500ms).

## Scope
**In:** ...
**Out (explicitly):** ...

## Constraints
Domain non-negotiables in play (as_of_date leakage rule, idempotent ingestion, async,
walk-forward validation, one model per stat), latency budgets, data availability,
playoff-mode quirks.

## Risks & unknowns
What could make this fail or leak data.

## Alternatives considered
At least one other approach and why it lost.
