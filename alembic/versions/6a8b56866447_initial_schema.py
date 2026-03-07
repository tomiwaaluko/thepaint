"""initial_schema

Revision ID: 6a8b56866447
Revises:
Create Date: 2026-03-07 00:21:39.454685

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6a8b56866447'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("team_id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("abbreviation", sa.String(5), nullable=False),
        sa.Column("conference", sa.String(10), nullable=False),
        sa.Column("division", sa.String(20), nullable=False),
        sa.Column("arena", sa.String(100)),
        sa.Column("city", sa.String(50), nullable=False),
    )

    op.create_table(
        "players",
        sa.Column("player_id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("team_id", sa.Integer, sa.ForeignKey("teams.team_id"), nullable=False),
        sa.Column("position", sa.String(5), nullable=False),
        sa.Column("height_inches", sa.Integer),
        sa.Column("weight_lbs", sa.Integer),
        sa.Column("birth_date", sa.Date),
        sa.Column("is_active", sa.Boolean, default=True),
    )

    op.create_table(
        "games",
        sa.Column("game_id", sa.String(20), primary_key=True),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("season", sa.String(10), nullable=False),
        sa.Column("home_team_id", sa.Integer, sa.ForeignKey("teams.team_id"), nullable=False),
        sa.Column("away_team_id", sa.Integer, sa.ForeignKey("teams.team_id"), nullable=False),
        sa.Column("is_playoffs", sa.Boolean, default=False),
        sa.Column("status", sa.String(20), default="scheduled"),
    )

    op.create_table(
        "player_game_logs",
        sa.Column("log_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("game_id", sa.String(20), sa.ForeignKey("games.game_id"), nullable=False),
        sa.Column("player_id", sa.Integer, sa.ForeignKey("players.player_id"), nullable=False),
        sa.Column("team_id", sa.Integer, sa.ForeignKey("teams.team_id"), nullable=False),
        sa.Column("game_date", sa.Date, nullable=False),
        sa.Column("season", sa.String(10), nullable=False),
        sa.Column("min_played", sa.Float, nullable=False),
        sa.Column("pts", sa.Integer, nullable=False),
        sa.Column("reb", sa.Integer, nullable=False),
        sa.Column("ast", sa.Integer, nullable=False),
        sa.Column("stl", sa.Integer, nullable=False),
        sa.Column("blk", sa.Integer, nullable=False),
        sa.Column("to_committed", sa.Integer, nullable=False),
        sa.Column("fg3m", sa.Integer, nullable=False),
        sa.Column("fg3a", sa.Integer, nullable=False),
        sa.Column("fgm", sa.Integer, nullable=False),
        sa.Column("fga", sa.Integer, nullable=False),
        sa.Column("ftm", sa.Integer, nullable=False),
        sa.Column("fta", sa.Integer, nullable=False),
        sa.Column("plus_minus", sa.Integer, nullable=False),
        sa.Column("starter", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("game_id", "player_id", name="uq_player_game"),
    )
    op.create_index("ix_player_game_date", "player_game_logs", ["player_id", "game_date"])
    op.create_index("ix_team_game_date_player", "player_game_logs", ["team_id", "game_date"])

    op.create_table(
        "team_game_logs",
        sa.Column("log_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("game_id", sa.String(20), sa.ForeignKey("games.game_id"), nullable=False),
        sa.Column("team_id", sa.Integer, sa.ForeignKey("teams.team_id"), nullable=False),
        sa.Column("game_date", sa.Date, nullable=False),
        sa.Column("season", sa.String(10), nullable=False),
        sa.Column("pts", sa.Integer, nullable=False),
        sa.Column("pace", sa.Float, nullable=False),
        sa.Column("off_rtg", sa.Float, nullable=False),
        sa.Column("def_rtg", sa.Float, nullable=False),
        sa.Column("ts_pct", sa.Float, nullable=False),
        sa.Column("ast", sa.Integer, nullable=False),
        sa.Column("to_committed", sa.Integer, nullable=False),
        sa.Column("oreb", sa.Integer, nullable=False),
        sa.Column("dreb", sa.Integer, nullable=False),
        sa.Column("fg3a_rate", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("game_id", "team_id", name="uq_team_game"),
    )
    op.create_index("ix_team_game_date", "team_game_logs", ["team_id", "game_date"])

    op.create_table(
        "injuries",
        sa.Column("injury_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("player_id", sa.Integer, sa.ForeignKey("players.player_id"), nullable=False),
        sa.Column("report_date", sa.Date, nullable=False),
        sa.Column("game_id", sa.String(20), sa.ForeignKey("games.game_id")),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_injury_player_date", "injuries", ["player_id", "report_date"])

    op.create_table(
        "betting_lines",
        sa.Column("line_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("game_id", sa.String(20), sa.ForeignKey("games.game_id"), nullable=False),
        sa.Column("player_id", sa.Integer, sa.ForeignKey("players.player_id")),
        sa.Column("sportsbook", sa.String(50), nullable=False),
        sa.Column("market", sa.String(50), nullable=False),
        sa.Column("line", sa.Float, nullable=False),
        sa.Column("over_odds", sa.Integer),
        sa.Column("under_odds", sa.Integer),
        sa.Column("timestamp", sa.DateTime, nullable=False),
    )
    op.create_index("ix_betting_game_market", "betting_lines", ["game_id", "market"])

    op.create_table(
        "predictions",
        sa.Column("pred_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("game_id", sa.String(20), sa.ForeignKey("games.game_id"), nullable=False),
        sa.Column("player_id", sa.Integer, sa.ForeignKey("players.player_id")),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("as_of_ts", sa.DateTime, nullable=False),
        sa.Column("stat", sa.String(20), nullable=False),
        sa.Column("p10", sa.Float, nullable=False),
        sa.Column("p25", sa.Float, nullable=False),
        sa.Column("p50", sa.Float, nullable=False),
        sa.Column("p75", sa.Float, nullable=False),
        sa.Column("p90", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_pred_game_player_stat", "predictions", ["game_id", "player_id", "stat"])


def downgrade() -> None:
    op.drop_table("predictions")
    op.drop_table("betting_lines")
    op.drop_table("injuries")
    op.drop_table("team_game_logs")
    op.drop_table("player_game_logs")
    op.drop_table("games")
    op.drop_table("players")
    op.drop_table("teams")
