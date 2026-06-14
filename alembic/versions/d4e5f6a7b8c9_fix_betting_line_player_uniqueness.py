"""fix_betting_line_player_uniqueness

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-14 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_betting_game_market_book", "betting_lines", type_="unique")
    op.execute(
        """
        WITH ranked AS (
            SELECT
                line_id,
                row_number() OVER (
                    PARTITION BY game_id, player_id, market, sportsbook
                    ORDER BY timestamp DESC, line_id DESC
                ) AS row_num
            FROM betting_lines
        )
        DELETE FROM betting_lines bl
        USING ranked r
        WHERE bl.line_id = r.line_id
          AND r.row_num > 1
        """
    )
    op.create_unique_constraint(
        "uq_betting_game_player_market_book",
        "betting_lines",
        ["game_id", "player_id", "market", "sportsbook"],
        postgresql_nulls_not_distinct=True,
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_betting_game_player_market_book",
        "betting_lines",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_betting_game_market_book",
        "betting_lines",
        ["game_id", "market", "sportsbook"],
    )
