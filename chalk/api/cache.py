"""Redis caching layer for predictions."""
import structlog
import redis.asyncio as aioredis

from pydantic import BaseModel

log = structlog.get_logger()

PREDICTION_CACHE_TTL = 900  # 15 minutes


async def get_cached(redis: aioredis.Redis, key: str, model_class: type[BaseModel]) -> BaseModel | None:
    """Get a cached Pydantic model from Redis."""
    try:
        cached = await redis.get(key)
        if cached:
            return model_class.model_validate_json(cached)
    except Exception as e:
        log.warning("cache_get_failed", key=key, error=str(e))
    return None


async def set_cached(
    redis: aioredis.Redis,
    key: str,
    value: BaseModel,
    ttl: int = PREDICTION_CACHE_TTL,
) -> None:
    """Cache a Pydantic model in Redis."""
    try:
        await redis.setex(key, ttl, value.model_dump_json())
    except Exception as e:
        log.warning("cache_set_failed", key=key, error=str(e))


async def invalidate_player_predictions(redis: aioredis.Redis, player_id: int) -> int:
    """Invalidate all cached predictions for a player. Returns count deleted."""
    try:
        pattern = f"pred:player:{player_id}:*"
        keys = await redis.keys(pattern)
        if keys:
            return await redis.delete(*keys)
    except Exception as e:
        log.warning("cache_invalidate_failed", player_id=player_id, error=str(e))
    return 0


async def invalidate_game_predictions(redis: aioredis.Redis, game_id: str) -> int:
    """Invalidate all cached predictions for a game. Returns count deleted."""
    try:
        pattern = f"pred:game:{game_id}*"
        keys = await redis.keys(pattern)
        if keys:
            return await redis.delete(*keys)
    except Exception as e:
        log.warning("cache_invalidate_failed", game_id=game_id, error=str(e))
    return 0
