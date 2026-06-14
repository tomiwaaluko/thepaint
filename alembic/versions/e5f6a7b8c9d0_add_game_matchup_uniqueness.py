"""add_game_matchup_uniqueness

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-14 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        WITH game_counts AS (
            SELECT
                g.game_id,
                g.date,
                g.home_team_id,
                g.away_team_id,
                count(pgl.log_id) AS player_log_count
            FROM games g
            LEFT JOIN player_game_logs pgl ON pgl.game_id = g.game_id
            GROUP BY g.game_id
        ),
        ranked AS (
            SELECT
                *,
                first_value(game_id) OVER (
                    PARTITION BY date, home_team_id, away_team_id
                    ORDER BY
                        player_log_count DESC,
                        CASE WHEN game_id LIKE '00%' THEN 0 ELSE 1 END,
                        game_id ASC
                ) AS canonical_game_id,
                count(*) OVER (
                    PARTITION BY date, home_team_id, away_team_id
                ) AS matchup_count
            FROM game_counts
        ),
        duplicate_map AS (
            SELECT game_id AS duplicate_game_id, canonical_game_id
            FROM ranked
            WHERE matchup_count > 1
              AND game_id <> canonical_game_id
        )
        DELETE FROM player_game_logs pgl
        USING duplicate_map dm
        WHERE pgl.game_id = dm.duplicate_game_id
          AND EXISTS (
              SELECT 1
              FROM player_game_logs canonical
              WHERE canonical.game_id = dm.canonical_game_id
                AND canonical.player_id = pgl.player_id
          )
        """
    )
    op.execute(
        """
        WITH game_counts AS (
            SELECT g.game_id, g.date, g.home_team_id, g.away_team_id, count(pgl.log_id) AS player_log_count
            FROM games g
            LEFT JOIN player_game_logs pgl ON pgl.game_id = g.game_id
            GROUP BY g.game_id
        ),
        ranked AS (
            SELECT *,
                first_value(game_id) OVER (
                    PARTITION BY date, home_team_id, away_team_id
                    ORDER BY player_log_count DESC, CASE WHEN game_id LIKE '00%' THEN 0 ELSE 1 END, game_id ASC
                ) AS canonical_game_id,
                count(*) OVER (PARTITION BY date, home_team_id, away_team_id) AS matchup_count
            FROM game_counts
        ),
        duplicate_map AS (
            SELECT game_id AS duplicate_game_id, canonical_game_id
            FROM ranked
            WHERE matchup_count > 1
              AND game_id <> canonical_game_id
        )
        UPDATE player_game_logs pgl
        SET game_id = dm.canonical_game_id
        FROM duplicate_map dm
        WHERE pgl.game_id = dm.duplicate_game_id
        """
    )
    op.execute(
        """
        WITH game_counts AS (
            SELECT g.game_id, g.date, g.home_team_id, g.away_team_id, count(pgl.log_id) AS player_log_count
            FROM games g
            LEFT JOIN player_game_logs pgl ON pgl.game_id = g.game_id
            GROUP BY g.game_id
        ),
        ranked AS (
            SELECT *,
                first_value(game_id) OVER (
                    PARTITION BY date, home_team_id, away_team_id
                    ORDER BY player_log_count DESC, CASE WHEN game_id LIKE '00%' THEN 0 ELSE 1 END, game_id ASC
                ) AS canonical_game_id,
                count(*) OVER (PARTITION BY date, home_team_id, away_team_id) AS matchup_count
            FROM game_counts
        ),
        duplicate_map AS (
            SELECT game_id AS duplicate_game_id, canonical_game_id
            FROM ranked
            WHERE matchup_count > 1
              AND game_id <> canonical_game_id
        )
        DELETE FROM team_game_logs tgl
        USING duplicate_map dm
        WHERE tgl.game_id = dm.duplicate_game_id
          AND EXISTS (
              SELECT 1
              FROM team_game_logs canonical
              WHERE canonical.game_id = dm.canonical_game_id
                AND canonical.team_id = tgl.team_id
          )
        """
    )
    op.execute(
        """
        WITH game_counts AS (
            SELECT g.game_id, g.date, g.home_team_id, g.away_team_id, count(pgl.log_id) AS player_log_count
            FROM games g
            LEFT JOIN player_game_logs pgl ON pgl.game_id = g.game_id
            GROUP BY g.game_id
        ),
        ranked AS (
            SELECT *,
                first_value(game_id) OVER (
                    PARTITION BY date, home_team_id, away_team_id
                    ORDER BY player_log_count DESC, CASE WHEN game_id LIKE '00%' THEN 0 ELSE 1 END, game_id ASC
                ) AS canonical_game_id,
                count(*) OVER (PARTITION BY date, home_team_id, away_team_id) AS matchup_count
            FROM game_counts
        ),
        duplicate_map AS (
            SELECT game_id AS duplicate_game_id, canonical_game_id
            FROM ranked
            WHERE matchup_count > 1
              AND game_id <> canonical_game_id
        )
        UPDATE team_game_logs tgl
        SET game_id = dm.canonical_game_id
        FROM duplicate_map dm
        WHERE tgl.game_id = dm.duplicate_game_id
        """
    )
    op.execute(
        """
        WITH game_counts AS (
            SELECT g.game_id, g.date, g.home_team_id, g.away_team_id, count(pgl.log_id) AS player_log_count
            FROM games g
            LEFT JOIN player_game_logs pgl ON pgl.game_id = g.game_id
            GROUP BY g.game_id
        ),
        ranked AS (
            SELECT *,
                first_value(game_id) OVER (
                    PARTITION BY date, home_team_id, away_team_id
                    ORDER BY player_log_count DESC, CASE WHEN game_id LIKE '00%' THEN 0 ELSE 1 END, game_id ASC
                ) AS canonical_game_id,
                count(*) OVER (PARTITION BY date, home_team_id, away_team_id) AS matchup_count
            FROM game_counts
        ),
        duplicate_map AS (
            SELECT game_id AS duplicate_game_id, canonical_game_id
            FROM ranked
            WHERE matchup_count > 1
              AND game_id <> canonical_game_id
        )
        UPDATE predictions p
        SET game_id = dm.canonical_game_id
        FROM duplicate_map dm
        WHERE p.game_id = dm.duplicate_game_id
        """
    )
    op.execute(
        """
        WITH game_counts AS (
            SELECT g.game_id, g.date, g.home_team_id, g.away_team_id, count(pgl.log_id) AS player_log_count
            FROM games g
            LEFT JOIN player_game_logs pgl ON pgl.game_id = g.game_id
            GROUP BY g.game_id
        ),
        ranked AS (
            SELECT *,
                first_value(game_id) OVER (
                    PARTITION BY date, home_team_id, away_team_id
                    ORDER BY player_log_count DESC, CASE WHEN game_id LIKE '00%' THEN 0 ELSE 1 END, game_id ASC
                ) AS canonical_game_id,
                count(*) OVER (PARTITION BY date, home_team_id, away_team_id) AS matchup_count
            FROM game_counts
        ),
        duplicate_map AS (
            SELECT game_id AS duplicate_game_id, canonical_game_id
            FROM ranked
            WHERE matchup_count > 1
              AND game_id <> canonical_game_id
        )
        UPDATE injuries i
        SET game_id = dm.canonical_game_id
        FROM duplicate_map dm
        WHERE i.game_id = dm.duplicate_game_id
        """
    )
    op.execute(
        """
        WITH game_counts AS (
            SELECT g.game_id, g.date, g.home_team_id, g.away_team_id, count(pgl.log_id) AS player_log_count
            FROM games g
            LEFT JOIN player_game_logs pgl ON pgl.game_id = g.game_id
            GROUP BY g.game_id
        ),
        ranked AS (
            SELECT *,
                first_value(game_id) OVER (
                    PARTITION BY date, home_team_id, away_team_id
                    ORDER BY player_log_count DESC, CASE WHEN game_id LIKE '00%' THEN 0 ELSE 1 END, game_id ASC
                ) AS canonical_game_id,
                count(*) OVER (PARTITION BY date, home_team_id, away_team_id) AS matchup_count
            FROM game_counts
        ),
        duplicate_map AS (
            SELECT game_id AS duplicate_game_id, canonical_game_id
            FROM ranked
            WHERE matchup_count > 1
              AND game_id <> canonical_game_id
        )
        DELETE FROM betting_lines bl
        USING duplicate_map dm
        WHERE bl.game_id = dm.duplicate_game_id
          AND EXISTS (
              SELECT 1
              FROM betting_lines canonical
              WHERE canonical.game_id = dm.canonical_game_id
                AND canonical.player_id IS NOT DISTINCT FROM bl.player_id
                AND canonical.market = bl.market
                AND canonical.sportsbook = bl.sportsbook
          )
        """
    )
    op.execute(
        """
        WITH game_counts AS (
            SELECT g.game_id, g.date, g.home_team_id, g.away_team_id, count(pgl.log_id) AS player_log_count
            FROM games g
            LEFT JOIN player_game_logs pgl ON pgl.game_id = g.game_id
            GROUP BY g.game_id
        ),
        ranked AS (
            SELECT *,
                first_value(game_id) OVER (
                    PARTITION BY date, home_team_id, away_team_id
                    ORDER BY player_log_count DESC, CASE WHEN game_id LIKE '00%' THEN 0 ELSE 1 END, game_id ASC
                ) AS canonical_game_id,
                count(*) OVER (PARTITION BY date, home_team_id, away_team_id) AS matchup_count
            FROM game_counts
        ),
        duplicate_map AS (
            SELECT game_id AS duplicate_game_id, canonical_game_id
            FROM ranked
            WHERE matchup_count > 1
              AND game_id <> canonical_game_id
        )
        UPDATE betting_lines bl
        SET game_id = dm.canonical_game_id
        FROM duplicate_map dm
        WHERE bl.game_id = dm.duplicate_game_id
        """
    )
    op.execute(
        """
        WITH game_counts AS (
            SELECT g.game_id, g.date, g.home_team_id, g.away_team_id, count(pgl.log_id) AS player_log_count
            FROM games g
            LEFT JOIN player_game_logs pgl ON pgl.game_id = g.game_id
            GROUP BY g.game_id
        ),
        ranked AS (
            SELECT *,
                first_value(game_id) OVER (
                    PARTITION BY date, home_team_id, away_team_id
                    ORDER BY player_log_count DESC, CASE WHEN game_id LIKE '00%' THEN 0 ELSE 1 END, game_id ASC
                ) AS canonical_game_id,
                count(*) OVER (PARTITION BY date, home_team_id, away_team_id) AS matchup_count
            FROM game_counts
        )
        DELETE FROM games g
        USING ranked r
        WHERE g.game_id = r.game_id
          AND r.matchup_count > 1
          AND r.game_id <> r.canonical_game_id
        """
    )
    op.create_unique_constraint(
        "uq_game_matchup",
        "games",
        ["date", "home_team_id", "away_team_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_game_matchup", "games", type_="unique")
