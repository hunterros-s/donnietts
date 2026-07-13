"""Keep only durable announcement run checkpoints.

Revision ID: 0006
Revises: 0005
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Speech generation has no audible side effect and is safe to retry after a
    # restart. Any process that stopped mid-generation should therefore look
    # planned again rather than persisting an uncertain runtime state.
    op.execute("UPDATE announcement_runs SET status = 'planned' WHERE status = 'generating'")

    with op.batch_alter_table("announcement_runs") as batch_op:
        batch_op.drop_constraint("ck_announcement_runs_status", type_="check")
        batch_op.drop_constraint("ck_announcement_runs_attempt_count", type_="check")
        batch_op.create_check_constraint(
            "ck_announcement_runs_status",
            "status IN ('planned', 'ready', 'playing', 'completed', 'failed', "
            "'skipped', 'cancelled', 'interrupted')",
        )
        batch_op.drop_column("generation_started_at")
        batch_op.drop_column("attempt_count")


def downgrade() -> None:
    with op.batch_alter_table("announcement_runs") as batch_op:
        batch_op.drop_constraint("ck_announcement_runs_status", type_="check")
        batch_op.create_check_constraint(
            "ck_announcement_runs_status",
            "status IN ('planned', 'generating', 'ready', 'playing', 'completed', "
            "'failed', 'skipped', 'cancelled', 'interrupted')",
        )
        batch_op.add_column(
            sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(
            sa.Column("generation_started_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_check_constraint(
            "ck_announcement_runs_attempt_count",
            "attempt_count >= 0",
        )
