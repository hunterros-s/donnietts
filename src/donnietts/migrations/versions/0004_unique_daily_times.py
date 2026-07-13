"""Require daily announcement times to be unique.

Revision ID: 0004
Revises: 0003
"""
from typing import Sequence

from alembic import op


revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_announcements_daily_minute",
        "announcements",
        ["minute_of_day"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_announcements_daily_minute", table_name="announcements")
