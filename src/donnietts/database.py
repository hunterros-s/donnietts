import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import event, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from donnietts.models import Announcement, ApplicationSettings
from donnietts.settings import ControllerSettings


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ApplicationSettingsSnapshot:
    announcements_enabled: bool
    timezone: str
    updated_at: datetime

    @property
    def mode(self) -> str:
        return "active" if self.announcements_enabled else "paused"


@dataclass(frozen=True)
class AnnouncementSnapshot:
    id: int
    kind: str
    enabled: bool
    minute_of_day: int | None
    run_at_utc: datetime | None
    template: str
    lead_seconds: int
    revision: int
    created_at: datetime
    updated_at: datetime

    @property
    def time(self) -> str | None:
        if self.minute_of_day is None:
            return None
        hour, minute = divmod(self.minute_of_day, 60)
        return f"{hour:02d}:{minute:02d}"


class Database:
    def __init__(self, settings: ControllerSettings):
        self.engine: AsyncEngine = create_async_engine(settings.database_url)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

        @event.listens_for(self.engine.sync_engine, "connect")
        def configure_sqlite(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    async def close(self) -> None:
        await self.engine.dispose()

    async def check_ready(self) -> tuple[bool, str | None]:
        try:
            await self.get_application_settings()
        except OperationalError as error:
            logger.warning("Database readiness check failed: %s", error)
            if "no such table" in str(error):
                return False, "Database schema is not initialized"
            return False, "Database is unavailable"
        except Exception as error:
            logger.warning("Database readiness check failed: %s", error)
            return False, "Database settings are unavailable"
        return True, None

    async def get_application_settings(self) -> ApplicationSettingsSnapshot:
        async with self.sessions() as session:
            row = await session.scalar(select(ApplicationSettings).where(ApplicationSettings.id == 1))
            if row is None:
                raise RuntimeError("Application settings have not been initialized")
            return self._settings_snapshot(row)

    async def update_application_settings(
        self,
        *,
        announcements_enabled: bool | None = None,
        timezone: str | None = None,
    ) -> ApplicationSettingsSnapshot:
        async with self.sessions.begin() as session:
            row = await session.get(ApplicationSettings, 1)
            if row is None:
                raise RuntimeError("Application settings have not been initialized")
            if announcements_enabled is not None:
                row.announcements_enabled = announcements_enabled
            if timezone is not None:
                row.timezone = timezone
            row.updated_at = datetime.now(UTC)
            await session.flush()
            return self._settings_snapshot(row)

    async def list_announcements(self) -> list[AnnouncementSnapshot]:
        async with self.sessions() as session:
            rows = await session.scalars(
                select(Announcement).order_by(
                    Announcement.kind,
                    Announcement.minute_of_day,
                    Announcement.run_at_utc,
                    Announcement.id,
                )
            )
            return [self._announcement_snapshot(row) for row in rows]

    @staticmethod
    def _settings_snapshot(row: ApplicationSettings) -> ApplicationSettingsSnapshot:
        updated_at = row.updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=UTC)
        return ApplicationSettingsSnapshot(
            announcements_enabled=row.announcements_enabled,
            timezone=row.timezone,
            updated_at=updated_at,
        )

    @classmethod
    def _announcement_snapshot(cls, row: Announcement) -> AnnouncementSnapshot:
        return AnnouncementSnapshot(
            id=row.id,
            kind=row.kind,
            enabled=row.enabled,
            minute_of_day=row.minute_of_day,
            run_at_utc=cls._as_utc(row.run_at_utc) if row.run_at_utc else None,
            template=row.template,
            lead_seconds=row.lead_seconds,
            revision=row.revision,
            created_at=cls._as_utc(row.created_at),
            updated_at=cls._as_utc(row.updated_at),
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is not None:
            return value
        return value.replace(tzinfo=UTC)
