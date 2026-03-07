"""Pydantic request/response schemas for the Chalk prediction API."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StatPrediction(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    stat: str
    p10: float
    p25: float
    p50: float = Field(..., alias="median")
    p75: float
    p90: float = Field(..., alias="ceiling")
    confidence: str  # "high" | "medium" | "low"


class FantasyScores(BaseModel):
    draftkings: float = 0.0
    fanduel: float = 0.0
    yahoo: float = 0.0


class InjuryContext(BaseModel):
    player_status: str = "active"  # "active" | "questionable" | "out"
    absent_teammates: list[str] = Field(default_factory=list)
    opportunity_adjustment: float = 1.0


class PlayerPredictionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    player_id: int
    player_name: str
    game_id: str
    opponent_team: str
    as_of_ts: datetime
    model_version: str
    predictions: list[StatPrediction]
    fantasy_scores: FantasyScores
    injury_context: InjuryContext


class TeamPredictionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    team_id: int
    team_name: str
    game_id: str
    opponent_team: str
    as_of_ts: datetime
    model_version: str
    predicted_pts: float
    predicted_pace: float
    predicted_off_rtg: float
    predicted_def_rtg: float


class GamePredictionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    game_id: str
    home_team: str
    away_team: str
    as_of_ts: datetime
    predicted_total: float
    home_predictions: list[PlayerPredictionResponse]
    away_predictions: list[PlayerPredictionResponse]


class OverUnderResponse(BaseModel):
    player_id: int
    player_name: str
    stat: str
    line: float
    sportsbook: str
    over_probability: float
    under_probability: float
    implied_over_prob: float
    edge: float
    confidence: str


class HealthResponse(BaseModel):
    status: str  # "ok" | "degraded"
    checks: dict[str, str]
    timestamp: datetime
