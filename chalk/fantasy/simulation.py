"""Monte Carlo simulation for fantasy floor/ceiling projections."""
from dataclasses import dataclass

import numpy as np

from chalk.api.schemas import StatPrediction
from chalk.fantasy.scoring import compute_fantasy_score


@dataclass
class SimulationResult:
    platform: str
    mean: float
    floor: float       # 10th percentile of simulated scores
    ceiling: float     # 90th percentile of simulated scores
    std: float
    boom_rate: float   # P(score >= 1.5x mean)
    bust_rate: float   # P(score <= 0.6x mean)


# Correlation structure between stats (driven by minutes)
# Order: pts, reb, ast, fg3m, stl, blk, to_committed
STAT_ORDER = ["pts", "reb", "ast", "fg3m", "stl", "blk", "to_committed"]
CORRELATION_MATRIX = np.array([
    # pts   reb   ast   fg3m  stl   blk   to
    [1.00, 0.25, 0.30, 0.40, 0.10, 0.05, 0.35],  # pts
    [0.25, 1.00, 0.15, 0.05, 0.10, 0.30, 0.10],  # reb
    [0.30, 0.15, 1.00, 0.15, 0.15, 0.05, 0.30],  # ast
    [0.40, 0.05, 0.15, 1.00, 0.05, 0.00, 0.10],  # fg3m
    [0.10, 0.10, 0.15, 0.05, 1.00, 0.10, 0.10],  # stl
    [0.05, 0.30, 0.05, 0.00, 0.10, 1.00, 0.05],  # blk
    [0.35, 0.10, 0.30, 0.10, 0.10, 0.05, 1.00],  # to
])


def _pred_to_params(pred: StatPrediction) -> tuple[float, float]:
    """Extract mean and std from a StatPrediction."""
    mean = pred.p50
    std = (pred.p90 - pred.p10) / 2.56  # normal approximation
    return mean, max(std, 0.1)


def simulate_fantasy_scores(
    stat_predictions: list[StatPrediction],
    platform: str,
    n_simulations: int = 1000,
    seed: int = 42,
) -> SimulationResult:
    """Run Monte Carlo simulation of fantasy scores.

    Samples correlated stat lines from prediction distributions,
    computes fantasy score for each, and returns percentile statistics.
    """
    rng = np.random.default_rng(seed)

    # Build prediction lookup
    pred_map = {p.stat: p for p in stat_predictions}

    # Build mean vector and std vector for available stats
    available_stats = [s for s in STAT_ORDER if s in pred_map]
    stat_indices = [STAT_ORDER.index(s) for s in available_stats]

    means = np.array([_pred_to_params(pred_map[s])[0] for s in available_stats])
    stds = np.array([_pred_to_params(pred_map[s])[1] for s in available_stats])

    # Extract sub-correlation matrix for available stats
    sub_corr = CORRELATION_MATRIX[np.ix_(stat_indices, stat_indices)]

    # Build covariance matrix from correlation + stds
    cov = np.outer(stds, stds) * sub_corr

    # Draw correlated samples
    samples = rng.multivariate_normal(means, cov, size=n_simulations)
    samples = np.maximum(samples, 0.0)  # floor at zero

    # Compute fantasy score for each simulation
    scores = np.zeros(n_simulations)
    for i in range(n_simulations):
        stat_dict = {stat: float(samples[i, j]) for j, stat in enumerate(available_stats)}
        scores[i] = compute_fantasy_score(stat_dict, platform)

    mean_score = float(np.mean(scores))

    return SimulationResult(
        platform=platform,
        mean=round(mean_score, 2),
        floor=round(float(np.percentile(scores, 10)), 2),
        ceiling=round(float(np.percentile(scores, 90)), 2),
        std=round(float(np.std(scores)), 2),
        boom_rate=round(float(np.mean(scores >= 1.5 * mean_score)), 3),
        bust_rate=round(float(np.mean(scores <= 0.6 * mean_score)), 3),
    )
