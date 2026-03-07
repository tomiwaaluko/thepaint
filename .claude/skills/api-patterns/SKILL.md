---
name: api-patterns
description: Use this skill whenever building or modifying any FastAPI code in Chalk. Covers route structure, request/response schemas, dependency injection, Redis caching, error handling, the prediction endpoint contract, and how confidence intervals and fantasy scores are returned. Always use this skill when touching chalk/api/, adding new routes, or changing response schemas.
---

# API Patterns Skill

## Route Structure

All routes are versioned under `/v1/`. Follow this URL pattern:
```
/v1/players/{player_id}/predict          ← player statline prediction
/v1/players/{player_id}/props            ← over/under probabilities vs. Vegas
/v1/games/{game_id}/predict              ← full game predictions (all players)
/v1/teams/{team_id}/predict              ← team stat prediction
/v1/fantasy/{game_id}                    ← fantasy scores for a game slate
/v1/health                               ← health check
```

---

## Response Schema Contract

Every prediction response MUST include point estimates AND confidence intervals.
This is the core differentiator for betting use cases — never return just a single number.

```python
from pydantic import BaseModel, Field
from datetime import datetime

class StatPrediction(BaseModel):
    stat: str                          # "pts", "reb", "ast", etc.
    p10: float                         # 10th percentile (floor)
    p25: float
    p50: float = Field(..., alias="median")   # primary prediction
    p75: float
    p90: float = Field(..., alias="ceiling")  # ceiling
    confidence: str                    # "high" | "medium" | "low"

class PlayerPredictionResponse(BaseModel):
    player_id: int
    player_name: str
    game_id: str
    opponent_team: str
    as_of_ts: datetime                 # when prediction was generated
    model_version: str
    predictions: list[StatPrediction]
    fantasy_scores: FantasyScores
    injury_context: InjuryContext

class FantasyScores(BaseModel):
    draftkings: float
    fanduel: float
    yahoo: float

class InjuryContext(BaseModel):
    player_status: str                 # "active" | "questionable" | "out"
    absent_teammates: list[str]        # names of out teammates
    opportunity_adjustment: float      # multiplier applied due to absences (1.0 = no change)

class OverUnderResponse(BaseModel):
    player_id: int
    player_name: str
    stat: str
    line: float                        # Vegas line
    sportsbook: str
    over_probability: float            # model's P(stat > line)
    under_probability: float
    implied_over_prob: float           # sportsbook implied probability from odds
    edge: float                        # over_probability - implied_over_prob
    confidence: str                    # "high" | "medium" | "low"
```

---

## Dependency Injection Pattern

```python
# chalk/api/dependencies.py
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from chalk.db.session import async_session_factory
import redis.asyncio as aioredis
from chalk.config import settings

async def get_db() -> AsyncSession:
    async with async_session_factory() as session:
        yield session

async def get_redis() -> aioredis.Redis:
    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()

# In routes:
@router.get("/players/{player_id}/predict")
async def predict_player(
    player_id: int,
    game_id: str,
    session: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> PlayerPredictionResponse:
    ...
```

---

## Redis Caching Pattern

Cache predictions for 15 minutes. Invalidate on injury report update.

```python
PREDICTION_CACHE_TTL = 900  # 15 minutes in seconds

async def get_cached_prediction(
    redis: aioredis.Redis,
    player_id: int,
    game_id: str,
) -> PlayerPredictionResponse | None:
    key = f"pred:player:{player_id}:game:{game_id}"
    cached = await redis.get(key)
    if cached:
        return PlayerPredictionResponse.model_validate_json(cached)
    return None

async def cache_prediction(
    redis: aioredis.Redis,
    player_id: int,
    game_id: str,
    response: PlayerPredictionResponse,
) -> None:
    key = f"pred:player:{player_id}:game:{game_id}"
    await redis.setex(key, PREDICTION_CACHE_TTL, response.model_dump_json())

async def invalidate_player_cache(redis: aioredis.Redis, player_id: int) -> None:
    """Call this when an injury report updates for a player or their teammate."""
    pattern = f"pred:player:{player_id}:*"
    keys = await redis.keys(pattern)
    if keys:
        await redis.delete(*keys)
```

---

## Full Route Implementation Pattern

```python
# chalk/api/routes/players.py
from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime

router = APIRouter(prefix="/v1/players", tags=["players"])

@router.get("/{player_id}/predict", response_model=PlayerPredictionResponse)
async def predict_player_statline(
    player_id: int,
    game_id: str = Query(..., description="NBA game ID from nba_api"),
    as_of: datetime | None = Query(None, description="Prediction as-of datetime (default: now)"),
    session: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> PlayerPredictionResponse:

    as_of_date = as_of or datetime.utcnow()

    # Check cache first
    cached = await get_cached_prediction(redis, player_id, game_id)
    if cached:
        return cached

    # Validate player + game exist
    player = await get_player_or_404(session, player_id)
    game = await get_game_or_404(session, game_id)

    # Generate features
    try:
        features = await generate_features(session, player_id, game_id, as_of_date)
    except FeatureError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Run predictions
    try:
        response = await build_player_prediction_response(
            session, player, game, features, as_of_date
        )
    except PredictionError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Cache and return
    await cache_prediction(redis, player_id, game_id, response)
    return response


async def get_player_or_404(session: AsyncSession, player_id: int):
    player = await session.get(Player, player_id)
    if not player:
        raise HTTPException(status_code=404, detail=f"Player {player_id} not found")
    return player
```

---

## Confidence Tier Logic

```python
def compute_confidence(
    p10: float,
    p90: float,
    line: float | None = None,
) -> str:
    """
    High: tight distribution (p90 - p10 < 10 for pts)
    Low: wide distribution OR line is inside the interquartile range
    """
    spread = p90 - p10
    stat_spreads = {"pts": 14, "reb": 8, "ast": 6}  # thresholds per stat

    if spread < stat_spreads.get("pts", 12) * 0.7:
        return "high"
    elif spread > stat_spreads.get("pts", 12) * 1.2:
        return "low"
    return "medium"
```

---

## Error Handling

Custom exceptions map to HTTP status codes in `main.py`:

```python
# chalk/api/main.py
from chalk.exceptions import IngestError, FeatureError, PredictionError

@app.exception_handler(FeatureError)
async def feature_error_handler(request, exc):
    return JSONResponse(status_code=422, content={"detail": str(exc), "type": "feature_error"})

@app.exception_handler(PredictionError)
async def prediction_error_handler(request, exc):
    return JSONResponse(status_code=500, content={"detail": str(exc), "type": "prediction_error"})
```

---

## Health Check

```python
@router.get("/health")
async def health(session: AsyncSession = Depends(get_db), redis: aioredis.Redis = Depends(get_redis)):
    checks = {}
    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"
    try:
        await redis.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"

    status = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": status, "checks": checks, "timestamp": datetime.utcnow()}
```

---

## Performance Targets

- p99 latency: < 500ms (cache hit: < 20ms)
- Never do N+1 queries in a single request — batch all DB calls
- Feature generation is the bottleneck — it must use a single optimized query, not a loop
- Use `asyncio.gather()` for independent feature fetches that can run in parallel

```python
# Parallel feature fetching
rolling, opponent, situational, roster = await asyncio.gather(
    get_all_rolling_features(session, player_id, as_of_date),
    get_opp_defensive_features(session, opponent_team_id, as_of_date),
    get_situational_features_async(session, game, player, as_of_date),
    get_roster_features(session, player_id, team_id, game_id, as_of_date),
)
```
