"""Tests for app-level exception handlers — 500s must not leak internals."""
import pytest
from httpx import ASGITransport, AsyncClient

from chalk.api.main import app
from chalk.exceptions import FeatureError, IngestError, PredictionError

SECRET_DETAIL = "asyncpg connect failed host=db.internal-secret.supabase.co user=postgres"


@pytest.fixture
def error_routes():
    """Temporarily mount routes that raise each custom exception."""

    @app.get("/test/prediction-error")
    async def _raise_prediction():
        raise PredictionError(SECRET_DETAIL)

    @app.get("/test/ingest-error")
    async def _raise_ingest():
        raise IngestError(SECRET_DETAIL)

    @app.get("/test/feature-error")
    async def _raise_feature():
        raise FeatureError("as_of_date is required")

    yield
    test_paths = {"/test/prediction-error", "/test/ingest-error", "/test/feature-error"}
    app.router.routes = [
        r for r in app.router.routes if getattr(r, "path", None) not in test_paths
    ]


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_prediction_error_returns_generic_500(error_routes):
    async with _client() as client:
        resp = await client.get("/test/prediction-error")
    assert resp.status_code == 500
    body = resp.json()
    assert body["type"] == "prediction_error"
    assert SECRET_DETAIL not in resp.text
    assert "supabase" not in resp.text


async def test_ingest_error_returns_generic_500(error_routes):
    async with _client() as client:
        resp = await client.get("/test/ingest-error")
    assert resp.status_code == 500
    body = resp.json()
    assert body["type"] == "ingest_error"
    assert SECRET_DETAIL not in resp.text
    assert "supabase" not in resp.text


async def test_feature_error_keeps_input_detail_422(error_routes):
    """4xx errors are input-related — meaningful detail is intentional."""
    async with _client() as client:
        resp = await client.get("/test/feature-error")
    assert resp.status_code == 422
    body = resp.json()
    assert body["type"] == "feature_error"
    assert body["detail"] == "as_of_date is required"
