"""Additional schemas for betting and fantasy routes."""
from dataclasses import dataclass

from pydantic import BaseModel, Field

from chalk.api.schemas import FantasyScores


class FantasyProjectionResponse(BaseModel):
    player_id: int
    player_name: str
    game_id: str
    platform: str
    fantasy_scores: FantasyScores
    floor: float
    ceiling: float
    mean: float
    std: float
    boom_rate: float
    bust_rate: float


class SlateFantasyResponse(BaseModel):
    game_id: str
    platform: str
    projections: list[FantasyProjectionResponse]
