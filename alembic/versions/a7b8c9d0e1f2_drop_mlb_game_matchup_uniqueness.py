"""drop mlb_games matchup uniqueness

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-06

Drops uq_mlb_game_matchup on mlb_games (date, home_team_id, away_team_id,
game_number). game_pk is the authoritative identity of an MLB game; MLB
assigns a distinct gamePk to a postponed game's makeup while reusing the same
date/teams/game_number, so multiple gamePks legitimately share that matchup
tuple. The constraint rejected those real makeup games and crashed the
backfill. Touches only the MLB tables, so it is safe on the shared DB.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_mlb_game_matchup", "mlb_games", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint(
        "uq_mlb_game_matchup",
        "mlb_games",
        ["date", "home_team_id", "away_team_id", "game_number"],
    )
