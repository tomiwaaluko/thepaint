class ChalkError(Exception):
    """Base exception for all Chalk errors."""


class IngestError(ChalkError):
    """Raised when data ingestion fails permanently."""


class FeatureError(ChalkError):
    """Raised when feature generation fails."""


class PredictionError(ChalkError):
    """Raised when prediction generation fails."""


class NotFoundError(PredictionError):
    """Raised when a requested entity does not exist.

    Distinct from a general PredictionError so route handlers can return a 404
    with the message intact WITHOUT that being a blanket licence to echo any
    exception text back to the caller.

    Messages on this class are authored here and contain only identifiers the
    caller already supplied ("Player 2544 not found"), so they are safe to
    return. A bare PredictionError may wrap upstream or driver text and is
    handled by the app-level sanitizing handler instead.

    Subclasses PredictionError so existing `except PredictionError` blocks keep
    working.
    """


class ModelNotFoundError(ChalkError):
    """Raised when a required ML model is not found in the registry."""
