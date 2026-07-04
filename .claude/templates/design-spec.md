# Design Spec — <feature title>

> The *shape* of the solution. Owned by phase 2 (`/chalk-plan`). Read the
> `planning-spec.md` first.

| | |
|---|---|
| **Branch** | `<prefix>/<slug>` |
| **Date** | YYYY-MM-DD |
| **Planning spec** | ./planning-spec.md |

## Approach
The chosen architecture in prose. Add a diagram if it helps.

## Component breakdown
Files/modules created or changed, each with its single responsibility. Use real
paths.

| Path | New / Changed | Responsibility |
|---|---|---|
| `chalk/features/...` | | |
| `chalk/api/routes/...` | | |

## Data flow
Trace one record/request end to end: ingest → feature → model → prediction → api →
dashboard (as applicable).

## Key design decisions
| Decision | Chosen | Rejected alternative | Why |
|---|---|---|---|
| | | | |

Honor the Chalk decisions where relevant: XGBoost over deep learning, one model per
stat, Opportunity Score recomputed at predict time, 3× recency weighting.

## Interfaces / contracts
Function signatures and types other modules will call. **Every feature-generating
function carries `as_of_date: datetime`.**

```python
async def <name>(session: AsyncSession, ..., as_of_date: datetime) -> <type>:
    ...
```

## Validation strategy
Walk-forward only — train 2015–2022, validate 2022–23, test 2023–24. Never k-fold.

## Open questions
Anything still to resolve before or during implementation.
