"""FastAPI app entrypoint for the Chalk NBA Prediction API."""
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from chalk.api.ratelimit import RateLimitMiddleware
from chalk.api.routes import fantasy, games, health, players, props, teams
from chalk.config import settings
from chalk.exceptions import FeatureError, IngestError, PredictionError

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-load all models into memory cache on startup."""
    from chalk.models.registry import load_model

    for stat in ["pts", "reb", "ast", "fg3m", "stl", "blk", "to_committed"]:
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

# CORS — origins controlled by the ALLOWED_ORIGINS env var (comma-separated).
#
# "*" is rejected rather than passed through. It is currently survivable
# because allow_credentials defaults to False, but the two settings live in
# different files and nothing couples them: adding allow_credentials=True below
# while ALLOWED_ORIGINS happened to be "*" would silently let any site on the
# internet make credentialed calls. Refuse the wildcard so that combination
# cannot be reached by accident.
_origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
if "*" in _origins:
    raise ValueError(
        'ALLOWED_ORIGINS must not contain "*". List the exact origins that '
        "should be permitted (comma-separated)."
    )
if not _origins:
    raise ValueError("ALLOWED_ORIGINS must list at least one origin.")


# Swagger UI and ReDoc are the only routes that legitimately render HTML and
# load scripts, so they cannot use the API's deny-everything CSP.
_HTML_DOC_PATHS = frozenset({"/docs", "/redoc", "/docs/oauth2-redirect"})


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=()"
        # Railway terminates TLS, so real traffic already arrives over HTTPS;
        # HSTS stops a downgrade attempt on the first hop.
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains"
        )
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"

        if request.url.path in _HTML_DOC_PATHS:
            # Swagger/ReDoc pull their assets from a CDN and bootstrap inline.
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https://fastapi.tiangolo.com; "
                "font-src 'self' https://cdn.jsdelivr.net; "
                "frame-ancestors 'none'; base-uri 'self'"
            )
        else:
            # JSON responses have no legitimate rendering context. If one is
            # ever coerced into being treated as a document, it still cannot
            # load scripts, styles, or any subresource.
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; "
                "form-action 'none'"
            )
        return response


# Innermost first: rate limiting runs inside the security/CORS layers so 429
# responses still carry security and CORS headers.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

# Include routers
app.include_router(health.router)
app.include_router(players.router)
app.include_router(teams.router)
app.include_router(games.router)
app.include_router(props.router)
app.include_router(fantasy.router)


# 422s keep meaningful (input-related) detail; 500s return a generic message
# and log the real error server-side — raw exception text can carry upstream
# URLs, hostnames, and driver errors that anonymous callers shouldn't see.


def _sanitize_log_value(value: str) -> str:
    """Escape CR/LF so attacker-controlled input can't forge log lines (CWE-117)."""
    return value.replace("\r", "\\r").replace("\n", "\\n")


@app.exception_handler(FeatureError)
async def feature_error_handler(request: Request, exc: FeatureError):
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc), "type": "feature_error"},
    )


@app.exception_handler(PredictionError)
async def prediction_error_handler(request: Request, exc: PredictionError):
    log.error(
        "prediction_error",
        path=_sanitize_log_value(request.url.path),
        error=_sanitize_log_value(str(exc)),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Prediction failed. Please try again later.", "type": "prediction_error"},
    )


@app.exception_handler(IngestError)
async def ingest_error_handler(request: Request, exc: IngestError):
    log.error(
        "ingest_error",
        path=_sanitize_log_value(request.url.path),
        error=_sanitize_log_value(str(exc)),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Data ingestion failed. Please try again later.", "type": "ingest_error"},
    )
