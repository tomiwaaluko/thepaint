"""Usage and role features."""
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.db.models import PlayerGameLog


async def get_usage_features(
    session: AsyncSession,
    player_id: int,
    as_of_date: date,
) -> dict[str, float]:
    """Compute usage and role features from last 10 games."""
    window = 10

    subq = (
        select(
            PlayerGameLog.min_played,
            PlayerGameLog.fga,
            PlayerGameLog.fta,
            PlayerGameLog.to_committed,
            PlayerGameLog.fg3a,
            PlayerGameLog.ast,
            PlayerGameLog.starter,
        )
        .where(PlayerGameLog.player_id == player_id)
        .where(PlayerGameLog.game_date < as_of_date)  # as_of_date gate
        .order_by(PlayerGameLog.game_date.desc())
        .limit(window)
    ).subquery()

    result = await session.execute(
        select(
            subq.c.min_played,
            subq.c.fga,
            subq.c.fta,
            subq.c.to_committed,
            subq.c.fg3a,
            subq.c.ast,
            subq.c.starter,
        )
    )
    rows = result.all()

    if not rows:
        return {
            "usage_rate_10g": 0.0,
            "min_share_10g": 0.0,
            "starter_rate_10g": 0.0,
            "fg3a_rate_10g": 0.0,
            "ft_rate_10g": 0.0,
            "ast_to_ratio_10g": 0.0,
        }

    total_min = sum(r.min_played for r in rows)
    total_fga = sum(r.fga for r in rows)
    total_fta = sum(r.fta for r in rows)
    total_tov = sum(r.to_committed for r in rows)
    total_fg3a = sum(r.fg3a for r in rows)
    total_ast = sum(r.ast for r in rows)
    starter_count = sum(1 for r in rows if r.starter)
    n = len(rows)

    avg_min = total_min / n

    # Usage rate proxy: (FGA + 0.44*FTA + TOV) / MIN * 36
    if total_min > 0:
        usage_rate = (total_fga + 0.44 * total_fta + total_tov) / total_min * 36
    else:
        usage_rate = 0.0

    # Min share: avg minutes / 48
    min_share = avg_min / 48.0

    # Starter rate
    starter_rate = starter_count / n

    # 3PA rate: fg3a / fga
    fg3a_rate = total_fg3a / total_fga if total_fga > 0 else 0.0

    # FT rate: fta / fga
    ft_rate = total_fta / total_fga if total_fga > 0 else 0.0

    # AST/TO ratio
    ast_to_ratio = total_ast / total_tov if total_tov > 0 else float(total_ast)

    return {
        "usage_rate_10g": float(usage_rate),
        "min_share_10g": float(min_share),
        "starter_rate_10g": float(starter_rate),
        "fg3a_rate_10g": float(fg3a_rate),
        "ft_rate_10g": float(ft_rate),
        "ast_to_ratio_10g": float(ast_to_ratio),
    }
