from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Integer, String, Text, func, true
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
