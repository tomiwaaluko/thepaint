"""Player prediction engine — generates full statline predictions."""
from datetime import date, datetime

import numpy as np
import pandas as pd
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.api.schemas import (
    FantasyScores,
    InjuryContext,
    PlayerPredictionResponse,
    StatPrediction,
)
from chalk.db.models import Game, Injury, Player, PlayerGameLog, Team
from chalk.exceptions import PredictionError
from chalk.features.pipeline import generate_features
from chalk.models.registry import get_model_version, load_model, load_quantile_models
from chalk.predictions.distributions import build_stat_prediction

log = structlog.get_logger()

POINT_STATS = ["pts", "reb", "ast", "fg3m"]
QUANTILE_STATS = {"pts", "reb", "ast"}
ALL_STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "to_committed"]


async def predict_player(
    session: AsyncSession,
    player_id: int,
    game_id: str,
    as_of_date: date,
) -> PlayerPredictionResponse:
    """Generate full statline prediction for a player in a game."""
    # Load player and game
    player = await session.get(Player, player_id)
    if not player:
        raise PredictionError(f"Player {player_id} not found")

    result = await session.execute(select(Game).where(Game.game_id == game_id))
    game = result.scalar_one_or_none()
    if not game:
        raise PredictionError(f"Game {game_id} not found")

    # Determine opponent
    if game.home_team_id == player.team_id:
        opp_team_id = game.away_team_id
    else:
        opp_team_id = game.home_team_id
    opp_result = await session.get(Team, opp_team_id)
    opponent_abbr = opp_result.abbreviation if opp_result else "UNK"

    # Generate features
    features = await generate_features(session, player_id, game_id, as_of_date)
    feature_df = pd.DataFrame([features])

    # Build predictions for each stat
    stat_predictions: list[StatPrediction] = []
    for stat in ALL_STATS:
        try:
            model = load_model(stat)
            # Align feature columns to what the model expects
            model_features = model.feature_names or list(feature_df.columns)
            X = _align_features(feature_df, model_features)
            point_pred = float(model.predict(X)[0])

            quantile_preds = None
            if stat in QUANTILE_STATS:
                try:
                    q_models = load_quantile_models(stat)
                    quantile_preds = {}
                    for q, q_model in q_models.items():
                        q_pred = float(q_model.predict(X)[0])
                        quantile_preds[q] = q_pred
                except Exception:
                    log.warning("quantile_model_load_failed", stat=stat)

            sp = build_stat_prediction(stat, quantile_preds, point_pred)
            stat_predictions.append(sp)
        except Exception as e:
            log.warning("stat_prediction_failed", stat=stat, error=str(e))
            continue

    if not stat_predictions:
        raise PredictionError(f"No models produced predictions for player {player_id}")

    # Fantasy scores
    fantasy = _compute_fantasy_scores(stat_predictions)

    # Injury context
    injury_ctx = await _get_injury_context(session, player_id, player.team_id, as_of_date)

    as_of_ts = datetime(as_of_date.year, as_of_date.month, as_of_date.day)

    return PlayerPredictionResponse(
        player_id=player_id,
        player_name=player.name,
        game_id=game_id,
        opponent_team=opponent_abbr,
        as_of_ts=as_of_ts,
        model_version=get_model_version("pts"),
        predictions=stat_predictions,
        fantasy_scores=fantasy,
        injury_context=injury_ctx,
    )


def _align_features(df: pd.DataFrame, expected_cols: list[str]) -> pd.DataFrame:
    """Align DataFrame columns to match model's expected features."""
    result = pd.DataFrame(index=df.index)
    for col in expected_cols:
        if col in df.columns:
            result[col] = df[col]
        else:
            result[col] = 0.0
    return result


def _get_stat_value(predictions: list[StatPrediction], stat: str) -> float:
    """Get p50 value for a stat from predictions list."""
    for p in predictions:
        if p.stat == stat:
            return p.p50
    return 0.0


def _compute_fantasy_scores(predictions: list[StatPrediction]) -> FantasyScores:
    """Compute DraftKings, FanDuel, Yahoo fantasy scores from stat predictions."""
    pts = _get_stat_value(predictions, "pts")
    reb = _get_stat_value(predictions, "reb")
    ast = _get_stat_value(predictions, "ast")
    stl = _get_stat_value(predictions, "stl")
    blk = _get_stat_value(predictions, "blk")
    to = _get_stat_value(predictions, "to_committed")
    fg3m = _get_stat_value(predictions, "fg3m")

    # DraftKings scoring
    dk = pts * 1.0 + fg3m * 0.5 + reb * 1.25 + ast * 1.5 + stl * 2.0 + blk * 2.0 + to * -0.5

    # FanDuel scoring
    fd = pts * 1.0 + reb * 1.2 + ast * 1.5 + stl * 3.0 + blk * 3.0 + to * -1.0

    # Yahoo scoring
    yahoo = pts * 1.0 + reb * 1.2 + ast * 1.5 + stl * 3.0 + blk * 3.0 + to * -1.0 + fg3m * 0.5

    return FantasyScores(
        draftkings=round(dk, 2),
        fanduel=round(fd, 2),
        yahoo=round(yahoo, 2),
    )


async def _get_injury_context(
    session: AsyncSession,
    player_id: int,
    team_id: int,
    as_of_date: date,
) -> InjuryContext:
    """Build injury context for a player prediction."""
    # Check player's own status
    result = await session.execute(
        select(Injury)
        .where(Injury.player_id == player_id)
        .where(Injury.report_date <= as_of_date)
        .order_by(Injury.report_date.desc())
        .limit(1)
    )
    own_injury = result.scalar_one_or_none()
    player_status = "active"
    if own_injury and own_injury.status in ("Out", "out"):
        player_status = "out"
    elif own_injury and own_injury.status in ("Questionable", "questionable", "Doubtful", "doubtful"):
        player_status = "questionable"

    # Find absent teammates
    result = await session.execute(
        select(Injury, Player)
        .join(Player, Injury.player_id == Player.player_id)
        .where(Player.team_id == team_id)
        .where(Injury.player_id != player_id)
        .where(Injury.report_date <= as_of_date)
        .where(Injury.status.in_(["Out", "out"]))
    )
    absent_rows = result.all()
    # Deduplicate by player — keep most recent report
    seen = set()
    absent_names = []
    for injury, player in absent_rows:
        if player.player_id not in seen:
            seen.add(player.player_id)
            absent_names.append(player.name)

    # Simple opportunity adjustment: +5% per absent teammate (capped at +25%)
    adj = min(1.25, 1.0 + 0.05 * len(absent_names))

    return InjuryContext(
        player_status=player_status,
        absent_teammates=absent_names,
        opportunity_adjustment=round(adj, 2),
    )
