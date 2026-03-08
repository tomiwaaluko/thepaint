"""fix_betting_lines_gameid_and_sportsbook_uniqueness

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-08 00:01:00.000000

The Odds API uses UUID-style game IDs (32+ chars) which don't match the
NBA-style game IDs stored in the games table. Remove the FK constraint and
widen game_id to VARCHAR(100). Also make the unique constraint include
sportsbook so we can store one row per (game, market, book).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the unique constraint we just added (wrong shape)
    op.drop_constraint("uq_betting_game_market", "betting_lines", type_="unique")

    # Drop the FK on game_id (Odds API IDs don't match games.game_id)
    op.drop_constraint("betting_lines_game_id_fkey", "betting_lines", type_="foreignkey")

    # Widen game_id to accommodate UUID-format IDs from Odds API
    op.alter_column("betting_lines", "game_id", type_=sa.String(100), existing_nullable=False)

    # New unique constraint includes sportsbook — one row per game+market+book
    op.create_unique_constraint(
        "uq_betting_game_market_book", "betting_lines",
        ["game_id", "market", "sportsbook"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_betting_game_market_book", "betting_lines", type_="unique")
    op.alter_column("betting_lines", "game_id", type_=sa.String(20), existing_nullable=False)
    op.create_foreign_key(
        "betting_lines_game_id_fkey", "betting_lines", "games", ["game_id"], ["game_id"]
    )
    op.create_unique_constraint(
        "uq_betting_game_market", "betting_lines", ["game_id", "market"]
    )
