"""Add the controller timezone setting.

Revision ID: 0003
Revises: 0002
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "application_settings",
        sa.Column(
            "timezone",
            sa.String(length=64),
            nullable=False,
            server_default="America/Detroit",
        ),
    )


def downgrade() -> None:
    op.drop_column("application_settings", "timezone")
