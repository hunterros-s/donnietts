"""Create singleton application settings.

Revision ID: 0001
Revises:
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    settings = op.create_table(
        "application_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("announcements_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.CheckConstraint("id = 1", name="ck_application_settings_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.bulk_insert(settings, [{"id": 1, "announcements_enabled": True}])


def downgrade() -> None:
    op.drop_table("application_settings")
