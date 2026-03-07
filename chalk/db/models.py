from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Team(Base):
    __tablename__ = "teams"

    team_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    abbreviation: Mapped[str] = mapped_column(String(5), nullable=False)
    conference: Mapped[str] = mapped_column(String(10), nullable=False)
    division: Mapped[str] = mapped_column(String(20), nullable=False)
    arena: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str] = mapped_column(String(50), nullable=False)

    players: Mapped[list["Player"]] = relationship(back_populates="team")


class Player(Base):
    __tablename__ = "players"

    player_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.team_id"), nullable=False)
    position: Mapped[str] = mapped_column(String(5), nullable=False)
    height_inches: Mapped[int | None] = mapped_column(Integer)
    weight_lbs: Mapped[int | None] = mapped_column(Integer)
    birth_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    team: Mapped["Team"] = relationship(back_populates="players")


class Game(Base):
    __tablename__ = "games"

    game_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    season: Mapped[str] = mapped_column(String(10), nullable=False)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.team_id"), nullable=False)
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.team_id"), nullable=False)
    is_playoffs: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="scheduled")

    home_team: Mapped["Team"] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped["Team"] = relationship(foreign_keys=[away_team_id])


class PlayerGameLog(Base):
    __tablename__ = "player_game_logs"
    __table_args__ = (
        UniqueConstraint("game_id", "player_id", name="uq_player_game"),
        Index("ix_player_game_date", "player_id", "game_date"),
        Index("ix_team_game_date_player", "team_id", "game_date"),
    )

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.game_id"), nullable=False)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.player_id"), nullable=False)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.team_id"), nullable=False)
    game_date: Mapped[date] = mapped_column(Date, nullable=False)
    season: Mapped[str] = mapped_column(String(10), nullable=False)
    min_played: Mapped[float] = mapped_column(Float, nullable=False)
    pts: Mapped[int] = mapped_column(Integer, nullable=False)
    reb: Mapped[int] = mapped_column(Integer, nullable=False)
    ast: Mapped[int] = mapped_column(Integer, nullable=False)
    stl: Mapped[int] = mapped_column(Integer, nullable=False)
    blk: Mapped[int] = mapped_column(Integer, nullable=False)
    to_committed: Mapped[int] = mapped_column(Integer, nullable=False)
    fg3m: Mapped[int] = mapped_column(Integer, nullable=False)
    fg3a: Mapped[int] = mapped_column(Integer, nullable=False)
    fgm: Mapped[int] = mapped_column(Integer, nullable=False)
    fga: Mapped[int] = mapped_column(Integer, nullable=False)
    ftm: Mapped[int] = mapped_column(Integer, nullable=False)
    fta: Mapped[int] = mapped_column(Integer, nullable=False)
    plus_minus: Mapped[int] = mapped_column(Integer, nullable=False)
    starter: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    game: Mapped["Game"] = relationship()
    player: Mapped["Player"] = relationship()
    team: Mapped["Team"] = relationship()


class TeamGameLog(Base):
    __tablename__ = "team_game_logs"
    __table_args__ = (
        UniqueConstraint("game_id", "team_id", name="uq_team_game"),
        Index("ix_team_game_date", "team_id", "game_date"),
    )

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.game_id"), nullable=False)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.team_id"), nullable=False)
    game_date: Mapped[date] = mapped_column(Date, nullable=False)
    season: Mapped[str] = mapped_column(String(10), nullable=False)
    pts: Mapped[int] = mapped_column(Integer, nullable=False)
    pace: Mapped[float] = mapped_column(Float, nullable=False)
    off_rtg: Mapped[float] = mapped_column(Float, nullable=False)
    def_rtg: Mapped[float] = mapped_column(Float, nullable=False)
    ts_pct: Mapped[float] = mapped_column(Float, nullable=False)
    ast: Mapped[int] = mapped_column(Integer, nullable=False)
    to_committed: Mapped[int] = mapped_column(Integer, nullable=False)
    oreb: Mapped[int] = mapped_column(Integer, nullable=False)
    dreb: Mapped[int] = mapped_column(Integer, nullable=False)
    fg3a_rate: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    game: Mapped["Game"] = relationship()
    team: Mapped["Team"] = relationship()


class Injury(Base):
    __tablename__ = "injuries"
    __table_args__ = (Index("ix_injury_player_date", "player_id", "report_date"),)

    injury_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.player_id"), nullable=False)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    game_id: Mapped[str | None] = mapped_column(ForeignKey("games.game_id"))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    player: Mapped["Player"] = relationship()


class BettingLine(Base):
    __tablename__ = "betting_lines"
    __table_args__ = (Index("ix_betting_game_market", "game_id", "market"),)

    line_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.game_id"), nullable=False)
    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.player_id"))
    sportsbook: Mapped[str] = mapped_column(String(50), nullable=False)
    market: Mapped[str] = mapped_column(String(50), nullable=False)
    line: Mapped[float] = mapped_column(Float, nullable=False)
    over_odds: Mapped[int | None] = mapped_column(Integer)
    under_odds: Mapped[int | None] = mapped_column(Integer)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (Index("ix_pred_game_player_stat", "game_id", "player_id", "stat"),)

    pred_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.game_id"), nullable=False)
    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.player_id"))
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    as_of_ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    stat: Mapped[str] = mapped_column(String(20), nullable=False)
    p10: Mapped[float] = mapped_column(Float, nullable=False)
    p25: Mapped[float] = mapped_column(Float, nullable=False)
    p50: Mapped[float] = mapped_column(Float, nullable=False)
    p75: Mapped[float] = mapped_column(Float, nullable=False)
    p90: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
