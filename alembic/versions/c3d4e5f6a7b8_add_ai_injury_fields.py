"""add_ai_injury_fields

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-16 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE injuries ADD COLUMN IF NOT EXISTS injury_type VARCHAR(100)")
    op.execute("ALTER TABLE injuries ADD COLUMN IF NOT EXISTS return_date DATE")
    op.execute("ALTER TABLE injuries ADD COLUMN IF NOT EXISTS notes VARCHAR(500)")


def downgrade() -> None:
    op.execute("ALTER TABLE injuries DROP COLUMN IF EXISTS notes")
    op.execute("ALTER TABLE injuries DROP COLUMN IF EXISTS return_date")
    op.execute("ALTER TABLE injuries DROP COLUMN IF EXISTS injury_type")
