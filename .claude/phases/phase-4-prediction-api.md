# Phase 4 — Prediction API

## Goal
FastAPI service with async endpoints that return full predicted statlines with confidence
intervals in under 500ms. Redis caching, injury-aware predictions, clean Pydantic schemas.

## Depends On
Phase 3 complete — models trained and registered in MLflow.

## Unlocks
Phase 5 (Betting & Fantasy) — adds routes on top of this API.
Phase 6 (Dashboard) — consumes this API.

## Skill Files to Read First
- `.claude/skills/api-patterns/SKILL.md` — all route patterns, schemas, caching, error handling
- `.claude/skills/mlflow-tracking/SKILL.md` — loading models from registry

---

## Step 1 — Pydantic Schemas

### `chalk/api/schemas.py`

Define all request and response models. Read `.claude/skills/api-patterns/SKILL.md` for the
full schema definitions before writing any code here.

**Schemas to define:**

`StatPrediction` — single stat with full percentile distribution + confidence tier
`PlayerPredictionResponse` — full player prediction with all stats + fantasy + injury context
`TeamPredictionResponse` — team-level game projection
`GamePredictionResponse` — all players in a game + team totals
`FantasyScores` — DK, FD, Yahoo projected scores
`InjuryContext` — player status, absent teammates, opportunity adjustment
`OverUnderResponse` — for Phase 5, define schema now even if route comes later
`HealthResponse` — DB and Redis status

**Rules:**
- All response models use `model_config = ConfigDict(populate_by_name=True)`
- Datetime fields serialize as ISO strings
- Float fields rounded to 2 decimal places in responses
- Never return None in a response — use 0.0 for missing floats, "" for missing strings

---

## Step 2 — App Dependencies

### `chalk/api/dependencies.py`

```python
async def get_db() -> AsyncSession     # yields async DB session
async def get_redis() -> aioredis.Redis  # yields Redis client
```

Both use async context managers. Redis client closed after request completes.

---

## Step 3 — Player Prediction Engine

### `chalk/predictions/player.py`

**Function: `predict_player(session, player_id, game_id, as_of_date) → PlayerPredictionResponse`**

Steps:
1. Load game and player from DB
2. Generate features via `generate_features(session, player_id, game_id, as_of_date)`
3. For each stat (pts, reb, ast, fg3m, stl, blk, to_committed):
   a. Load median model from registry: `load_model(stat)`
   b. Load quantile models: `load_quantile_models(stat)` (for pts, reb, ast only)
   c. Run predictions → get p50 from median model, p10/p25/p75/p90 from quantile models
   d. For stats without quantile models: estimate intervals as p50 ± 1 MAE
4. Build `StatPrediction` for each stat
5. Compute fantasy scores via `compute_fantasy_scores(stat_predictions)`
6. Build injury context via `get_injury_context(session, player_id, game_id, as_of_date)`
7. Return `PlayerPredictionResponse`

**Confidence tier logic:**
```python
def compute_confidence(stat: str, p10: float, p90: float) -> str:
    spread = p90 - p10
    thresholds = {"pts": 14, "reb": 8, "ast": 6, "fg3m": 3}
    threshold = thresholds.get(stat, 10)
    if spread < threshold * 0.7: return "high"
    if spread > threshold * 1.3: return "low"
    return "medium"
```

---

## Step 4 — Distribution Builder

### `chalk/predictions/distributions.py`

**Functions:**

`build_stat_prediction(stat, quantile_preds, median_pred, point_pred_fallback) → StatPrediction`
- Assembles StatPrediction from model outputs
- Validates p10 < p25 < p50 < p75 < p90 (fix ordering if quantile crossing occurs)

`fix_quantile_crossing(predictions: dict[float, float]) → dict[float, float]`
- If quantile models produce crossed predictions (p25 > p50), fix by isotonic regression
- This happens occasionally — must be handled

`estimate_interval_from_mae(p50: float, stat: str) → tuple[float, float]`
- For stats without quantile models, estimate p10 and p90 from historical MAE
- p10 ≈ p50 - 1.5 * MAE, p90 ≈ p50 + 1.5 * MAE (approximation)

---

## Step 5 — Team Prediction Engine

### `chalk/predictions/team.py`

**Function: `predict_team(session, team_id, game_id, as_of_date) → TeamPredictionResponse`**

Predicts: total points for the team, pace, implied game total.

---

## Step 6 — FastAPI App Setup

### `chalk/api/main.py`

```python
app = FastAPI(
    title="Chalk NBA Prediction API",
    version="1.0.0",
    docs_url="/docs",
)

# Include routers
app.include_router(players_router)
app.include_router(teams_router)
app.include_router(games_router)
app.include_router(health_router)

# Exception handlers for custom exceptions
# Startup event: warm up model cache (load all models from MLflow on startup)
# Shutdown event: close DB connections
```

**Startup model warmup:**
```python
@app.on_event("startup")
async def warmup_models():
    """Pre-load all models from MLflow into memory cache on startup."""
    for stat in ["pts", "reb", "ast", "fg3m", "stl", "blk", "to_committed"]:
        load_model(stat)
    log.info("models_warmed_up")
```

---

## Step 7 — Routes

### `chalk/api/routes/players.py`

**`GET /v1/players/{player_id}/predict`**

Query params:
- `game_id: str` (required)
- `as_of: datetime | None` (optional, defaults to now)

Logic:
1. Check Redis cache → return if hit
2. Call `predict_player(session, player_id, game_id, as_of_date)`
3. Cache result with 15-minute TTL
4. Return PlayerPredictionResponse

Cache key: `pred:player:{player_id}:game:{game_id}`

**`GET /v1/players/{player_id}/history`**

Returns last 10 actual game logs for a player — useful for dashboard context.

### `chalk/api/routes/games.py`

**`GET /v1/games/{game_id}/predict`**

Returns predictions for all active players in a game.
- Load all player_game_logs participants from the game's team rosters
- Call `predict_player()` for each, concurrently via `asyncio.gather()`
- Cache full game prediction for 15 minutes
- Cache key: `pred:game:{game_id}`

### `chalk/api/routes/teams.py`

**`GET /v1/teams/{team_id}/predict`**

Query param: `game_id: str`

### `chalk/api/routes/health.py`

**`GET /v1/health`**

Returns DB ping status, Redis ping status, model registry status, timestamp.

---

## Step 8 — Redis Caching

Implement full caching layer following `.claude/skills/api-patterns/SKILL.md`:

```python
CACHE_TTL = 900  # 15 minutes

async def get_cached(redis, key: str, model_class) -> BaseModel | None
async def set_cached(redis, key: str, value: BaseModel, ttl: int = CACHE_TTL) -> None
async def invalidate_player_predictions(redis, player_id: int) -> None
async def invalidate_game_predictions(redis, game_id: str) -> None
```

`invalidate_player_predictions()` is called by the injury feed when a player's status changes.
This ensures stale predictions (based on pre-injury lineup) are never served.

---

## Step 9 — Tests

### `tests/test_api/test_players.py`

Use `httpx.AsyncClient` with FastAPI test app.

`test_predict_player_returns_correct_schema`
- Mock generate_features() and load_model()
- Verify response matches PlayerPredictionResponse schema exactly
- Verify all stat predictions present

`test_predict_player_cache_hit`
- Call endpoint twice
- Verify predict_player() called only once (cache served second call)

`test_predict_player_404_on_unknown_player`

`test_predict_player_injury_context_populated`
- Mock absent teammate
- Verify InjuryContext.absent_teammates contains the player name

### `tests/test_api/test_health.py`

`test_health_returns_ok_when_all_services_up`
`test_health_returns_degraded_when_redis_down`

---

## Phase 4 Completion Checklist

- [ ] `pytest tests/test_api/` — all tests pass
- [ ] `GET /v1/players/2544/predict?game_id=...` returns valid PlayerPredictionResponse
- [ ] All 7 stats present in response with p10–p90 distributions
- [ ] Redis cache working — second call returns cache hit
- [ ] Cache invalidates when `invalidate_player_predictions()` called
- [ ] Model warmup on startup — no cold load during first request
- [ ] p99 latency < 500ms (verify with a simple load test: 100 requests, measure p99)
- [ ] `/v1/health` returns correct status
- [ ] Exception handlers return proper JSON error responses
- [ ] `TODO.md` updated — all Phase 4 checkboxes marked done
