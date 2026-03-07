"""Over/under probability computation from quantile distributions."""
import numpy as np
from scipy import stats as sp_stats

import structlog

log = structlog.get_logger()


def fit_distribution(
    p10: float, p25: float, p50: float, p75: float, p90: float,
) -> sp_stats.rv_continuous:
    """Fit a continuous distribution to 5 quantile points.

    Uses normal distribution with mean=p50, std estimated from the 10-90 spread.
    Returns a frozen scipy distribution object.
    """
    std = (p90 - p10) / 2.56  # 2.56 = z(0.90) - z(0.10) for normal
    if std <= 0:
        std = 0.1  # minimum spread
    return sp_stats.norm(loc=p50, scale=std)


def over_probability(
    line: float, p10: float, p25: float, p50: float, p75: float, p90: float,
) -> float:
    """Return P(stat > line) using a fitted distribution.

    Result clamped to [0.01, 0.99] — never returns 0% or 100%.
    """
    dist = fit_distribution(p10, p25, p50, p75, p90)
    prob = 1.0 - dist.cdf(line)
    return float(np.clip(prob, 0.01, 0.99))


def american_to_implied_probability(odds: int) -> float:
    """Convert American odds to implied probability.

    -110 → 0.524, +120 → 0.455, +100 → 0.500, etc.
    """
    if odds < 0:
        return abs(odds) / (abs(odds) + 100)
    else:
        return 100 / (odds + 100)


def remove_vig(over_implied: float, under_implied: float) -> tuple[float, float]:
    """Remove vig from implied probabilities to get true probabilities.

    Sportsbook probabilities sum to > 1.0 due to vig. Normalize to 1.0.
    """
    total = over_implied + under_implied
    if total <= 0:
        return 0.5, 0.5
    return over_implied / total, under_implied / total


def calculate_edge(over_prob: float, implied_prob: float) -> float:
    """Calculate betting edge: model probability minus implied probability.

    Positive = model favors over. Negative = model favors under.
    """
    return round(over_prob - implied_prob, 4)


def edge_confidence(edge: float) -> str:
    """Map edge magnitude to confidence tier."""
    abs_edge = abs(edge)
    if abs_edge >= 0.08:
        return "high"
    if abs_edge >= 0.04:
        return "medium"
    return "low"
