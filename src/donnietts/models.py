from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    true,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ApplicationSettings(Base):
    __tablename__ = "application_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_application_settings_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    announcements_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )
    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="America/Detroit",
        server_default="America/Detroit",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )


class Announcement(Base):
    __tablename__ = "announcements"
    __table_args__ = (
        CheckConstraint("kind IN ('daily', 'one_off')", name="ck_announcements_kind"),
        CheckConstraint("lead_seconds >= 0", name="ck_announcements_lead_seconds"),
        CheckConstraint("revision >= 1", name="ck_announcements_revision"),
        CheckConstraint(
            "(kind = 'daily' AND minute_of_day BETWEEN 0 AND 1439 AND run_at_utc IS NULL) "
            "OR (kind = 'one_off' AND minute_of_day IS NULL AND run_at_utc IS NOT NULL)",
            name="ck_announcements_schedule_shape",
        ),
        Index("ix_announcements_kind_enabled", "kind", "enabled"),
        Index("uq_announcements_daily_minute", "minute_of_day", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )
    minute_of_day: Mapped[int | None] = mapped_column(Integer)
    run_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    template: Mapped[str] = mapped_column(Text, nullable=False)
    lead_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )


class AnnouncementRun(Base):
    __tablename__ = "announcement_runs"
    __table_args__ = (
        CheckConstraint(
            "announcement_kind IN ('daily', 'one_off')",
            name="ck_announcement_runs_kind",
        ),
        CheckConstraint(
            "status IN ('planned', 'generating', 'ready', 'playing', 'completed', "
            "'failed', 'skipped', 'cancelled', 'interrupted')",
            name="ck_announcement_runs_status",
        ),
        CheckConstraint(
            "announcement_revision >= 1",
            name="ck_announcement_runs_revision",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_announcement_runs_attempt_count"),
        CheckConstraint(
            "generation_due_at_utc <= scheduled_for_utc",
            name="ck_announcement_runs_generation_before_schedule",
        ),
        Index(
            "uq_announcement_runs_occurrence",
            "announcement_id",
            "scheduled_for_utc",
            unique=True,
        ),
        Index(
            "ix_announcement_runs_status_generation_due",
            "status",
            "generation_due_at_utc",
        ),
        Index(
            "ix_announcement_runs_status_scheduled_for",
            "status",
            "scheduled_for_utc",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    announcement_id: Mapped[int | None] = mapped_column(
        ForeignKey("announcements.id", ondelete="SET NULL"),
        nullable=True,
    )
    announcement_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    announcement_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    scheduled_for_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    generation_due_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="planned",
        server_default="planned",
    )
    template_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    rendered_text: Mapped[str | None] = mapped_column(Text)
    audio_path: Mapped[str | None] = mapped_column(Text)
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    error: Mapped[str | None] = mapped_column(Text)
    outcome_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )
    generation_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    playback_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
