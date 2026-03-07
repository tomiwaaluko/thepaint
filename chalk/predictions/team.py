"""Team prediction engine — generates team-level game projections."""
from datetime import date, datetime

import pandas as pd
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.api.schemas import TeamPredictionResponse
from chalk.db.models import Game, Team, TeamGameLog
from chalk.exceptions import PredictionError
from chalk.models.registry import get_model_version, load_model

log = structlog.get_logger()


async def predict_team(
    session: AsyncSession,
    team_id: int,
    game_id: str,
    as_of_date: date,
) -> TeamPredictionResponse:
    """Generate team-level prediction for a game."""
    team = await session.get(Team, team_id)
    if not team:
        raise PredictionError(f"Team {team_id} not found")

    result = await session.execute(select(Game).where(Game.game_id == game_id))
    game = result.scalar_one_or_none()
    if not game:
        raise PredictionError(f"Game {game_id} not found")

    if game.home_team_id == team_id:
        opp_team_id = game.away_team_id
    else:
        opp_team_id = game.home_team_id
    opp_team = await session.get(Team, opp_team_id)
    opponent_name = opp_team.name if opp_team else "Unknown"

    # Build team features from recent game logs
    features = await _build_team_features(session, team_id, opp_team_id, game, as_of_date)
    feature_df = pd.DataFrame([features])

    # Predict using team model
    try:
        model = load_model("team_total")
        model_features = model.feature_names or list(feature_df.columns)
        X = pd.DataFrame(index=feature_df.index)
        for col in model_features:
            X[col] = feature_df[col] if col in feature_df.columns else 0.0
        predicted_total = float(model.predict(X)[0])
    except Exception as e:
        log.warning("team_model_prediction_failed", error=str(e))
        predicted_total = 0.0

    as_of_ts = datetime(as_of_date.year, as_of_date.month, as_of_date.day)

    return TeamPredictionResponse(
        team_id=team_id,
        team_name=team.name,
        game_id=game_id,
        opponent_team=opponent_name,
        as_of_ts=as_of_ts,
        model_version=get_model_version("team_total"),
        predicted_pts=round(predicted_total / 2, 1),
        predicted_pace=features.get("home_pace_avg_10g", 100.0),
        predicted_off_rtg=features.get("home_off_rtg_avg_10g", 110.0),
        predicted_def_rtg=features.get("home_def_rtg_avg_10g", 110.0),
    )


async def _build_team_features(
    session: AsyncSession,
    team_id: int,
    opp_team_id: int,
    game: Game,
    as_of_date: date,
) -> dict[str, float]:
    """Build feature dict for team prediction from recent game logs."""
    features: dict[str, float] = {}
    is_home = game.home_team_id == team_id

    for prefix, tid in [("home", team_id if is_home else opp_team_id),
                         ("away", opp_team_id if is_home else team_id)]:
        result = await session.execute(
            select(TeamGameLog)
            .where(TeamGameLog.team_id == tid)
            .where(TeamGameLog.game_date < as_of_date)
            .order_by(TeamGameLog.game_date.desc())
            .limit(20)
        )
        logs = result.scalars().all()

        for window in [10, 20]:
            subset = logs[:window]
            if not subset:
                for col in ["pts", "pace", "off_rtg", "def_rtg"]:
                    features[f"{prefix}_{col}_avg_{window}g"] = 0.0
                continue
            features[f"{prefix}_pts_avg_{window}g"] = sum(l.pts for l in subset) / len(subset)
            features[f"{prefix}_pace_avg_{window}g"] = sum(l.pace for l in subset) / len(subset)
            features[f"{prefix}_off_rtg_avg_{window}g"] = sum(l.off_rtg for l in subset) / len(subset)
            features[f"{prefix}_def_rtg_avg_{window}g"] = sum(l.def_rtg for l in subset) / len(subset)

    features["is_home"] = 1.0 if is_home else 0.0
    return features
