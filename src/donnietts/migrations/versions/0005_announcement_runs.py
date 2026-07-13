"""Create durable announcement runs.

Revision ID: 0005
Revises: 0004
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "announcement_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("announcement_id", sa.Integer(), nullable=True),
        sa.Column("announcement_revision", sa.Integer(), nullable=False),
        sa.Column("announcement_kind", sa.String(length=16), nullable=False),
        sa.Column("scheduled_for_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generation_due_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="planned"),
        sa.Column("template_snapshot", sa.Text(), nullable=False),
        sa.Column("rendered_text", sa.Text(), nullable=True),
        sa.Column("audio_path", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("outcome_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column("generation_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("playback_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "announcement_kind IN ('daily', 'one_off')",
            name="ck_announcement_runs_kind",
        ),
        sa.CheckConstraint(
            "status IN ('planned', 'generating', 'ready', 'playing', 'completed', "
            "'failed', 'skipped', 'cancelled', 'interrupted')",
            name="ck_announcement_runs_status",
        ),
        sa.CheckConstraint(
            "announcement_revision >= 1",
            name="ck_announcement_runs_revision",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_announcement_runs_attempt_count"),
        sa.CheckConstraint(
            "generation_due_at_utc <= scheduled_for_utc",
            name="ck_announcement_runs_generation_before_schedule",
        ),
        sa.ForeignKeyConstraint(
            ["announcement_id"],
            ["announcements.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_announcement_runs_occurrence",
        "announcement_runs",
        ["announcement_id", "scheduled_for_utc"],
        unique=True,
    )
    op.create_index(
        "ix_announcement_runs_status_generation_due",
        "announcement_runs",
        ["status", "generation_due_at_utc"],
        unique=False,
    )
    op.create_index(
        "ix_announcement_runs_status_scheduled_for",
        "announcement_runs",
        ["status", "scheduled_for_utc"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_announcement_runs_status_scheduled_for",
        table_name="announcement_runs",
    )
    op.drop_index(
        "ix_announcement_runs_status_generation_due",
        table_name="announcement_runs",
    )
    op.drop_index(
        "uq_announcement_runs_occurrence",
        table_name="announcement_runs",
    )
    op.drop_table("announcement_runs")
