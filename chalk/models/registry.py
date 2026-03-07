"""Model registry — save/load trained models from disk."""
from functools import lru_cache
from pathlib import Path

import structlog
import xgboost as xgb

from chalk.models.base import BaseStatModel

log = structlog.get_logger()

MODEL_DIR = Path("models")

REGISTERED_MODEL_NAMES = {
    "pts": "chalk-player-pts",
    "reb": "chalk-player-reb",
    "ast": "chalk-player-ast",
    "fg3m": "chalk-player-fg3m",
    "stl": "chalk-player-stl",
    "blk": "chalk-player-blk",
    "to_committed": "chalk-player-to",
    "team_total": "chalk-team-total",
    "pace": "chalk-team-pace",
}


def _model_path(stat: str) -> Path:
    return MODEL_DIR / f"{stat}_model.joblib"


def _quantile_path(stat: str, quantile: float) -> Path:
    return MODEL_DIR / f"{stat}_q{int(quantile * 100)}_model.joblib"


def save_model(model: BaseStatModel) -> Path:
    """Save a trained model to disk."""
    path = _model_path(model.stat)
    model.save(path)
    log.info("model_saved", stat=model.stat, path=str(path))
    return path


def save_quantile_model(stat: str, quantile: float, model: xgb.XGBRegressor) -> Path:
    """Save a quantile model to disk."""
    import joblib
    path = _quantile_path(stat, quantile)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)
    log.info("quantile_model_saved", stat=stat, quantile=quantile, path=str(path))
    return path


@lru_cache(maxsize=None)
def load_model(stat: str) -> BaseStatModel:
    """Load latest model for a stat. Cached in memory."""
    path = _model_path(stat)
    return BaseStatModel.load(path)


def load_quantile_models(stat: str) -> dict[float, xgb.XGBRegressor]:
    """Load all 5 quantile models for a stat."""
    import joblib
    quantiles = [0.10, 0.25, 0.50, 0.75, 0.90]
    return {
        q: joblib.load(_quantile_path(stat, q))
        for q in quantiles
    }


def get_model_version(stat: str) -> str:
    """Return version string based on model file modification time."""
    path = _model_path(stat)
    if path.exists():
        mtime = path.stat().st_mtime
        from datetime import datetime
        return datetime.fromtimestamp(mtime).strftime("%Y%m%d_%H%M%S")
    return "unknown"


def invalidate_cache() -> None:
    """Clear cached models — call after retraining."""
    load_model.cache_clear()
