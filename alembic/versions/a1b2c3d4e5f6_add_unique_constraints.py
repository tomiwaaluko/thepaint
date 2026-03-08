"""add_unique_constraints_to_injuries_and_betting_lines

Revision ID: a1b2c3d4e5f6
Revises: 6a8b56866447
Create Date: 2026-03-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '6a8b56866447'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # injuries: replace plain index with unique constraint so ON CONFLICT works
    op.drop_index("ix_injury_player_date", table_name="injuries")
    op.create_unique_constraint(
        "uq_injury_player_date", "injuries", ["player_id", "report_date"]
    )

    # betting_lines: replace plain index with unique constraint so ON CONFLICT works
    op.drop_index("ix_betting_game_market", table_name="betting_lines")
    op.create_unique_constraint(
        "uq_betting_game_market", "betting_lines", ["game_id", "market"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_betting_game_market", "betting_lines", type_="unique")
    op.create_index("ix_betting_game_market", "betting_lines", ["game_id", "market"])

    op.drop_constraint("uq_injury_player_date", "injuries", type_="unique")
    op.create_index("ix_injury_player_date", "injuries", ["player_id", "report_date"])
