"""add mlb tables

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-04

Purely additive: creates the five MLB tables (teams, players, games,
batter/pitcher game logs). No existing table is touched, so this is safe to
apply to the shared production database.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mlb_teams",
        sa.Column("team_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("abbreviation", sa.String(length=5), nullable=False),
        sa.Column("league", sa.String(length=20), nullable=False),
        sa.Column("division", sa.String(length=30), nullable=False),
        sa.Column("venue", sa.String(length=100), nullable=True),
        sa.Column("city", sa.String(length=50), nullable=False),
    )

    op.create_table(
        "mlb_players",
        sa.Column("player_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "team_id", sa.Integer(), sa.ForeignKey("mlb_teams.team_id"), nullable=True
        ),
        sa.Column("position", sa.String(length=5), nullable=False),
        sa.Column("bats", sa.String(length=1), nullable=True),
        sa.Column("throws", sa.String(length=1), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.create_table(
        "mlb_games",
        sa.Column("game_pk", sa.Integer(), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("season", sa.String(length=4), nullable=False),
        sa.Column("game_type", sa.String(length=1), nullable=False),
        sa.Column(
            "is_postseason", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "doubleheader", sa.String(length=1), nullable=False, server_default="N"
        ),
        sa.Column("game_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "home_team_id", sa.Integer(), sa.ForeignKey("mlb_teams.team_id"), nullable=False
        ),
        sa.Column(
            "away_team_id", sa.Integer(), sa.ForeignKey("mlb_teams.team_id"), nullable=False
        ),
        sa.Column(
            "status", sa.String(length=30), nullable=False, server_default="scheduled"
        ),
        sa.Column("venue", sa.String(length=100), nullable=True),
        sa.UniqueConstraint(
            "date", "home_team_id", "away_team_id", "game_number",
            name="uq_mlb_game_matchup",
        ),
    )

    op.create_table(
        "mlb_batter_game_logs",
        sa.Column("log_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "game_pk", sa.Integer(), sa.ForeignKey("mlb_games.game_pk"), nullable=False
        ),
        sa.Column(
            "player_id", sa.Integer(), sa.ForeignKey("mlb_players.player_id"), nullable=False
        ),
        sa.Column(
            "team_id", sa.Integer(), sa.ForeignKey("mlb_teams.team_id"), nullable=False
        ),
        sa.Column("game_date", sa.Date(), nullable=False),
        sa.Column("season", sa.String(length=4), nullable=False),
        sa.Column("ab", sa.Integer(), nullable=False),
        sa.Column("r", sa.Integer(), nullable=False),
        sa.Column("h", sa.Integer(), nullable=False),
        sa.Column("doubles", sa.Integer(), nullable=False),
        sa.Column("triples", sa.Integer(), nullable=False),
        sa.Column("hr", sa.Integer(), nullable=False),
        sa.Column("rbi", sa.Integer(), nullable=False),
        sa.Column("bb", sa.Integer(), nullable=False),
        sa.Column("so", sa.Integer(), nullable=False),
        sa.Column("sb", sa.Integer(), nullable=False),
        sa.Column("cs", sa.Integer(), nullable=False),
        sa.Column("hbp", sa.Integer(), nullable=False),
        sa.Column("total_bases", sa.Integer(), nullable=False),
        sa.Column("plate_appearances", sa.Integer(), nullable=False),
        sa.Column("batting_order", sa.String(length=3), nullable=True),
        sa.Column("position", sa.String(length=5), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=True, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=True, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("game_pk", "player_id", name="uq_mlb_batter_game"),
    )
    op.create_index(
        "ix_mlb_batter_player_date", "mlb_batter_game_logs", ["player_id", "game_date"]
    )
    op.create_index(
        "ix_mlb_batter_team_date", "mlb_batter_game_logs", ["team_id", "game_date"]
    )

    op.create_table(
        "mlb_pitcher_game_logs",
        sa.Column("log_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "game_pk", sa.Integer(), sa.ForeignKey("mlb_games.game_pk"), nullable=False
        ),
        sa.Column(
            "player_id", sa.Integer(), sa.ForeignKey("mlb_players.player_id"), nullable=False
        ),
        sa.Column(
            "team_id", sa.Integer(), sa.ForeignKey("mlb_teams.team_id"), nullable=False
        ),
        sa.Column("game_date", sa.Date(), nullable=False),
        sa.Column("season", sa.String(length=4), nullable=False),
        sa.Column("is_starter", sa.Boolean(), nullable=False),
        sa.Column("outs_recorded", sa.Integer(), nullable=False),
        sa.Column("h", sa.Integer(), nullable=False),
        sa.Column("r", sa.Integer(), nullable=False),
        sa.Column("er", sa.Integer(), nullable=False),
        sa.Column("bb", sa.Integer(), nullable=False),
        sa.Column("so", sa.Integer(), nullable=False),
        sa.Column("hr", sa.Integer(), nullable=False),
        sa.Column("batters_faced", sa.Integer(), nullable=False),
        sa.Column("pitches_thrown", sa.Integer(), nullable=False),
        sa.Column("win", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("loss", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("save", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("hold", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(), nullable=True, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=True, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("game_pk", "player_id", name="uq_mlb_pitcher_game"),
    )
    op.create_index(
        "ix_mlb_pitcher_player_date", "mlb_pitcher_game_logs", ["player_id", "game_date"]
    )
    op.create_index(
        "ix_mlb_pitcher_team_date", "mlb_pitcher_game_logs", ["team_id", "game_date"]
    )


def downgrade() -> None:
    # Drop in FK-safe order: logs → games → players → teams.
    op.drop_index("ix_mlb_pitcher_team_date", table_name="mlb_pitcher_game_logs")
    op.drop_index("ix_mlb_pitcher_player_date", table_name="mlb_pitcher_game_logs")
    op.drop_table("mlb_pitcher_game_logs")
    op.drop_index("ix_mlb_batter_team_date", table_name="mlb_batter_game_logs")
    op.drop_index("ix_mlb_batter_player_date", table_name="mlb_batter_game_logs")
    op.drop_table("mlb_batter_game_logs")
    op.drop_table("mlb_games")
    op.drop_table("mlb_players")
    op.drop_table("mlb_teams")
