"""FastAPI app entrypoint for the Chalk NBA Prediction API."""
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from chalk.api.routes import fantasy, games, health, players, props, teams
from chalk.config import settings
from chalk.exceptions import FeatureError, IngestError, PredictionError

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-load all models into memory cache on startup."""
    from chalk.models.registry import load_model

    for stat in ["pts", "reb", "ast", "fg3m"]:
        try:
            load_model(stat)
            log.info("model_loaded", stat=stat)
        except Exception as e:
            log.warning("model_load_failed", stat=stat, error=str(e))
    log.info("models_warmup_complete")
    yield


app = FastAPI(
    title="Chalk NBA Prediction API",
    version="1.0.0",
    docs_url="/docs",
    lifespan=lifespan,
)

# CORS — origins controlled by ALLOWED_ORIGINS env var (comma-separated or "*")
_origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router)
app.include_router(players.router)
app.include_router(teams.router)
app.include_router(games.router)
app.include_router(props.router)
app.include_router(fantasy.router)


@app.exception_handler(FeatureError)
async def feature_error_handler(request, exc):
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc), "type": "feature_error"},
    )


@app.exception_handler(PredictionError)
async def prediction_error_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "type": "prediction_error"},
    )


@app.exception_handler(IngestError)
async def ingest_error_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "type": "ingest_error"},
    )
