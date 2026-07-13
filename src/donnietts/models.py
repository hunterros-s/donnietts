from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, func, true
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
