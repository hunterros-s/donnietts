import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import event, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from donnietts.models import ApplicationSettings
from donnietts.settings import ControllerSettings


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ApplicationSettingsSnapshot:
    announcements_enabled: bool
    updated_at: datetime

    @property
    def mode(self) -> str:
        return "active" if self.announcements_enabled else "paused"


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
            return self._snapshot(row)

    async def set_announcements_enabled(self, enabled: bool) -> ApplicationSettingsSnapshot:
        async with self.sessions.begin() as session:
            row = await session.get(ApplicationSettings, 1)
            if row is None:
                raise RuntimeError("Application settings have not been initialized")
            row.announcements_enabled = enabled
            row.updated_at = datetime.now(UTC)
            await session.flush()
            return self._snapshot(row)

    @staticmethod
    def _snapshot(row: ApplicationSettings) -> ApplicationSettingsSnapshot:
        updated_at = row.updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=UTC)
        return ApplicationSettingsSnapshot(
            announcements_enabled=row.announcements_enabled,
            updated_at=updated_at,
        )
