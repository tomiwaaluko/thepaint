"""MLB ORM table definitions.

All tables share the project-wide declarative ``Base`` (chalk.db.models) so a
single Alembic metadata covers both sports. Game identity is the upstream MLB
StatsAPI ``gamePk`` — never date+teams, which doubleheaders make ambiguous.
Batter and pitcher lines live in separate tables so a two-way player can have
one row in each for the same game.
"""
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from chalk.db.models import Base


class MlbTeam(Base):
    __tablename__ = "mlb_teams"

    # Upstream StatsAPI id — never generated locally.
    team_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    abbreviation: Mapped[str] = mapped_column(String(5), nullable=False)
    # Nullable: stub rows upserted for FK safety carry only id+name until a
    # full ingest_mlb_teams run fills the metadata — NULL is an honest
    # "not yet known", unlike an empty-string sentinel.
    league: Mapped[str | None] = mapped_column(String(20))
    division: Mapped[str | None] = mapped_column(String(30))
    venue: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str | None] = mapped_column(String(50))

    players: Mapped[list["MlbPlayer"]] = relationship(back_populates="team")


class MlbPlayer(Base):
    __tablename__ = "mlb_players"

    player_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Last-seen team; null tolerated (free agents, releases).
    team_id: Mapped[int | None] = mapped_column(ForeignKey("mlb_teams.team_id"))
    position: Mapped[str] = mapped_column(String(5), nullable=False)
    bats: Mapped[str | None] = mapped_column(String(1))
    throws: Mapped[str | None] = mapped_column(String(1))
    birth_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    team: Mapped["MlbTeam | None"] = relationship(back_populates="players")


class MlbGame(Base):
    __tablename__ = "mlb_games"
    # game_pk is the authoritative identity of an MLB game. We deliberately do
    # NOT add a (date, home, away, game_number) uniqueness constraint: MLB
    # assigns a distinct gamePk to a postponed game's makeup while reusing the
    # same date/teams/game_number, so multiple gamePks legitimately share that
    # matchup tuple. Enforcing uniqueness on it rejects real makeup games.

    game_pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    season: Mapped[str] = mapped_column(String(4), nullable=False)
    # R = regular season; F/D/L/W = postseason rounds (wild card → World Series).
    game_type: Mapped[str] = mapped_column(String(1), nullable=False)
    is_postseason: Mapped[bool] = mapped_column(Boolean, default=False)
    doubleheader: Mapped[str] = mapped_column(String(1), default="N")
    game_number: Mapped[int] = mapped_column(Integer, default=1)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("mlb_teams.team_id"), nullable=False)
    away_team_id: Mapped[int] = mapped_column(ForeignKey("mlb_teams.team_id"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="scheduled")
    # Upstream's coarse state machine: Preview / Live / Final. The canonical
    # "is this game over" signal; status (detailedState) is display detail.
    abstract_state: Mapped[str | None] = mapped_column(String(20))
    venue: Mapped[str | None] = mapped_column(String(100))

    home_team: Mapped["MlbTeam"] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped["MlbTeam"] = relationship(foreign_keys=[away_team_id])


class MlbBatterGameLog(Base):
    __tablename__ = "mlb_batter_game_logs"
    __table_args__ = (
        UniqueConstraint("game_pk", "player_id", name="uq_mlb_batter_game"),
        Index("ix_mlb_batter_player_date", "player_id", "game_date"),
        Index("ix_mlb_batter_team_date", "team_id", "game_date"),
    )

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_pk: Mapped[int] = mapped_column(ForeignKey("mlb_games.game_pk"), nullable=False)
    player_id: Mapped[int] = mapped_column(ForeignKey("mlb_players.player_id"), nullable=False)
    team_id: Mapped[int] = mapped_column(ForeignKey("mlb_teams.team_id"), nullable=False)
    game_date: Mapped[date] = mapped_column(Date, nullable=False)
    season: Mapped[str] = mapped_column(String(4), nullable=False)
    ab: Mapped[int] = mapped_column(Integer, nullable=False)
    r: Mapped[int] = mapped_column(Integer, nullable=False)
    h: Mapped[int] = mapped_column(Integer, nullable=False)
    doubles: Mapped[int] = mapped_column(Integer, nullable=False)
    triples: Mapped[int] = mapped_column(Integer, nullable=False)
    hr: Mapped[int] = mapped_column(Integer, nullable=False)
    rbi: Mapped[int] = mapped_column(Integer, nullable=False)
    bb: Mapped[int] = mapped_column(Integer, nullable=False)
    so: Mapped[int] = mapped_column(Integer, nullable=False)
    sb: Mapped[int] = mapped_column(Integer, nullable=False)
    cs: Mapped[int] = mapped_column(Integer, nullable=False)
    hbp: Mapped[int] = mapped_column(Integer, nullable=False)
    total_bases: Mapped[int] = mapped_column(Integer, nullable=False)
    plate_appearances: Mapped[int] = mapped_column(Integer, nullable=False)
    # Upstream slot encoding kept verbatim: starters "100".."900", subs "101" etc.
    batting_order: Mapped[str | None] = mapped_column(String(3))
    position: Mapped[str] = mapped_column(String(5), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    game: Mapped["MlbGame"] = relationship()
    player: Mapped["MlbPlayer"] = relationship()
    team: Mapped["MlbTeam"] = relationship()


class MlbPitcherGameLog(Base):
    __tablename__ = "mlb_pitcher_game_logs"
    __table_args__ = (
        UniqueConstraint("game_pk", "player_id", name="uq_mlb_pitcher_game"),
        Index("ix_mlb_pitcher_player_date", "player_id", "game_date"),
        Index("ix_mlb_pitcher_team_date", "team_id", "game_date"),
    )

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_pk: Mapped[int] = mapped_column(ForeignKey("mlb_games.game_pk"), nullable=False)
    player_id: Mapped[int] = mapped_column(ForeignKey("mlb_players.player_id"), nullable=False)
    team_id: Mapped[int] = mapped_column(ForeignKey("mlb_teams.team_id"), nullable=False)
    game_date: Mapped[date] = mapped_column(Date, nullable=False)
    season: Mapped[str] = mapped_column(String(4), nullable=False)
    is_starter: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # Innings pitched is base-3 notation ("6.2" = 6 innings 2 outs), so outs are
    # stored as an exact integer; IP is derivable, never stored as a float.
    outs_recorded: Mapped[int] = mapped_column(Integer, nullable=False)
    h: Mapped[int] = mapped_column(Integer, nullable=False)
    r: Mapped[int] = mapped_column(Integer, nullable=False)
    er: Mapped[int] = mapped_column(Integer, nullable=False)
    bb: Mapped[int] = mapped_column(Integer, nullable=False)
    so: Mapped[int] = mapped_column(Integer, nullable=False)
    hr: Mapped[int] = mapped_column(Integer, nullable=False)
    batters_faced: Mapped[int] = mapped_column(Integer, nullable=False)
    pitches_thrown: Mapped[int] = mapped_column(Integer, nullable=False)
    win: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    loss: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    save: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hold: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    game: Mapped["MlbGame"] = relationship()
    player: Mapped["MlbPlayer"] = relationship()
    team: Mapped["MlbTeam"] = relationship()
