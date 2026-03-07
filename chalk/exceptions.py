class ChalkError(Exception):
    """Base exception for all Chalk errors."""


class IngestError(ChalkError):
    """Raised when data ingestion fails permanently."""


class FeatureError(ChalkError):
    """Raised when feature generation fails."""


class PredictionError(ChalkError):
    """Raised when prediction generation fails."""


class ModelNotFoundError(ChalkError):
    """Raised when a required ML model is not found in the registry."""
