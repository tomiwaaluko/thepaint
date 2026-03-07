"""Master feature pipeline — single entry point for all feature generation."""
from datetime import date

import pandas as pd
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.db.models import Game, Player, PlayerGameLog
from chalk.exceptions import FeatureError
from chalk.features.opponent import get_all_opponent_features
from chalk.features.rolling import get_all_rolling_features
from chalk.features.roster import get_roster_features
from chalk.features.situational import (
    get_game_number_in_season,
    get_previous_game_date,
    get_situational_features,
)
from chalk.features.usage import get_usage_features

log = structlog.get_logger()


async def _get_game(session: AsyncSession, game_id: str) -> Game:
    result = await session.execute(
        select(Game).where(Game.game_id == game_id)
    )
    game = result.scalar_one_or_none()
    if game is None:
        raise FeatureError(f"Game {game_id} not found")
    return game


async def _get_player(session: AsyncSession, player_id: int) -> Player:
    result = await session.execute(
        select(Player).where(Player.player_id == player_id)
    )
    player = result.scalar_one_or_none()
    if player is None:
        raise FeatureError(f"Player {player_id} not found")
    return player


def _get_opponent_id(game: Game, team_id: int) -> int:
    if game.home_team_id == team_id:
        return game.away_team_id
    return game.home_team_id


async def generate_features(
    session: AsyncSession,
    player_id: int,
    game_id: str,
    as_of_date: date,
) -> dict[str, float]:
    """Generate the complete feature vector for a player-game pair.

    Returns flat dict of ~80+ float features. No None values.

    Raises:
        FeatureError: If player or game not found.
    """
    game = await _get_game(session, game_id)
    player = await _get_player(session, player_id)
    opponent_team_id = _get_opponent_id(game, player.team_id)

    # Run feature groups sequentially (asyncpg requires single-query-per-connection)
    rolling = await get_all_rolling_features(session, player_id, as_of_date)
    opponent = await get_all_opponent_features(session, opponent_team_id, player.position, as_of_date)
    roster = await get_roster_features(session, player_id, player.team_id, opponent_team_id, game_id, as_of_date)
    usage = await get_usage_features(session, player_id, as_of_date)
    prev_date = await get_previous_game_date(session, player_id, as_of_date)
    game_num = await get_game_number_in_season(session, player.team_id, game.season, as_of_date)

    # Situational is synchronous
    situational = get_situational_features(game, player, prev_date, game_num)

    features = {**rolling, **opponent, **roster, **usage, **situational}

    # Replace any None values with 0.0 and ensure all are float
    features = {k: float(v) if v is not None else 0.0 for k, v in features.items()}

    return features


async def build_training_matrix(
    session: AsyncSession,
    player_ids: list[int],
    stat: str,
    seasons: list[str],
) -> pd.DataFrame:
    """Build a training matrix: features + target for every player × game.

    Returns DataFrame with feature columns, target column, and metadata.
    """
    rows = []

    for pid in player_ids:
        # Fetch all game logs for this player in the given seasons
        result = await session.execute(
            select(PlayerGameLog)
            .where(PlayerGameLog.player_id == pid)
            .where(PlayerGameLog.season.in_(seasons))
            .order_by(PlayerGameLog.game_date.asc())
        )
        logs = result.scalars().all()

        for game_log in logs:
            try:
                features = await generate_features(
                    session, pid, game_log.game_id, game_log.game_date,
                )
            except FeatureError:
                continue

            target_val = getattr(game_log, stat, None)
            if target_val is None:
                continue

            features["target"] = float(target_val)
            features["player_id"] = float(pid)
            features["game_id"] = game_log.game_id
            features["game_date"] = game_log.game_date.isoformat()
            features["season"] = game_log.season
            rows.append(features)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    log.info("training_matrix_built", rows=len(df), features=len(df.columns) - 5)
    return df
