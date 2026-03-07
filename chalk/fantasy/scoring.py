"""Fantasy scoring engine — DraftKings, FanDuel, Yahoo."""
from chalk.api.schemas import FantasyScores

SCORING = {
    "draftkings": {
        "pts": 1.0,
        "fg3m": 0.5,
        "reb": 1.25,
        "ast": 1.5,
        "stl": 2.0,
        "blk": 2.0,
        "to_committed": -0.5,
        "double_double_bonus": 1.5,
        "triple_double_bonus": 3.0,
    },
    "fanduel": {
        "pts": 1.0,
        "reb": 1.2,
        "ast": 1.5,
        "stl": 2.0,
        "blk": 2.0,
        "to_committed": -1.0,
    },
    "yahoo": {
        "pts": 1.0,
        "fg3m": 0.5,
        "reb": 1.2,
        "ast": 1.5,
        "stl": 2.0,
        "blk": 2.0,
        "to_committed": -1.0,
    },
}

STAT_KEYS = {"pts", "fg3m", "reb", "ast", "stl", "blk", "to_committed"}
DD_ELIGIBLE = ["pts", "reb", "ast", "stl", "blk"]


def compute_fantasy_score(stats: dict[str, float], platform: str) -> float:
    """Compute fantasy score for a platform given a stat dict."""
    scoring = SCORING[platform]
    score = sum(
        stats.get(stat, 0.0) * mult
        for stat, mult in scoring.items()
        if stat in STAT_KEYS
    )

    # DraftKings double-double / triple-double bonuses
    if platform == "draftkings":
        double_digit_count = sum(
            1 for s in DD_ELIGIBLE if stats.get(s, 0.0) >= 10
        )
        if double_digit_count >= 2:
            score += scoring["double_double_bonus"]
        if double_digit_count >= 3:
            score += scoring["triple_double_bonus"]

    return round(score, 2)


def compute_all_fantasy_scores(stats: dict[str, float]) -> FantasyScores:
    """Compute fantasy scores for all three platforms."""
    return FantasyScores(
        draftkings=compute_fantasy_score(stats, "draftkings"),
        fanduel=compute_fantasy_score(stats, "fanduel"),
        yahoo=compute_fantasy_score(stats, "yahoo"),
    )
