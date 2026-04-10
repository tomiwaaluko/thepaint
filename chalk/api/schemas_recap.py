"""Pydantic schemas for the predictions recap endpoint."""
from datetime import date

from pydantic import BaseModel


class RecapStatComparison(BaseModel):
    stat: str
    predicted: float  # p50
    actual: int
    p10: float
    p25: float
    p75: float
    p90: float
    error: float  # abs(actual - predicted)
    grade: str  # "hit" | "close" | "miss"


class RecapPlayerEntry(BaseModel):
    player_id: int
    player_name: str
    team_abbreviation: str
    position: str
    stats: list[RecapStatComparison]
    hit_count: int
    close_count: int
    miss_count: int


class RecapGameEntry(BaseModel):
    game_id: str
    date: date
    home_team: str
    away_team: str
    home_score: int | None = None
    away_score: int | None = None
    players: list[RecapPlayerEntry]
    game_mae: float
    game_hit_rate: float


class RecapSummary(BaseModel):
    total_predictions: int
    hit_rate: float
    close_rate: float
    miss_rate: float
    mae_by_stat: dict[str, float]
    overall_mae: float


class RecapResponse(BaseModel):
    date: date
    summary: RecapSummary
    games: list[RecapGameEntry]
