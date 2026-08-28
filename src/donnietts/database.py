import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, event, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from donnietts.announcement_runs import AnnouncementRunRepository, CANCELLABLE_STATUSES
from donnietts.models import Announcement, AnnouncementRun, ApplicationSettings, Base
from donnietts.settings import ControllerSettings

if TYPE_CHECKING:
    from donnietts.schedule import Schedule, ScheduleAnnouncement


logger = logging.getLogger(__name__)


class AnnouncementNotFoundError(RuntimeError):
    pass


class AnnouncementRevisionConflictError(RuntimeError):
    pass


class DuplicateDailyTimeError(RuntimeError):
    pass


class AnnouncementKindMismatchError(RuntimeError):
    pass


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
        self.settings = settings
        self.engine: AsyncEngine = create_async_engine(settings.database_url)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.runs = AnnouncementRunRepository(self.sessions)

        @event.listens_for(self.engine.sync_engine, "connect")
        def configure_sqlite(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    async def initialize(self) -> None:
        """Create the schema and singleton settings row if they do not exist."""
        self.settings.database_path.parent.mkdir(parents=True, exist_ok=True)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        try:
            async with self.sessions.begin() as session:
                if await session.get(ApplicationSettings, 1) is None:
                    session.add(
                        ApplicationSettings(
                            id=1,
                            announcements_enabled=True,
                            timezone="America/Detroit",
                        )
                    )
        except IntegrityError:
            # Another process created the settings row concurrently.
            pass

    async def close(self) -> None:
        await self.engine.dispose()

    async def check_ready(self) -> tuple[bool, str | None]:
        try:
            await self.get_application_settings()
        except RuntimeError:
            return False, "Application settings are not initialized"
        except OperationalError as error:
            logger.warning("Database readiness check failed: %s", error)
            if "no such table" in str(error):
                return False, "Database schema is not initialized"
            return False, "Database is unavailable"
        except Exception as error:
            logger.warning("Database readiness check failed: %s", error)
            return False, "Application settings are unavailable"
        return True, None

    async def get_application_settings(self) -> ApplicationSettingsSnapshot:
        async with self.sessions() as session:
            row = await session.scalar(
                select(ApplicationSettings).where(ApplicationSettings.id == 1)
            )
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

    async def sync_schedule(self, schedule: "Schedule") -> list[AnnouncementSnapshot]:
        """Make the announcement projection match a validated YAML schedule.

        SQLite remains responsible for durable runs and operational settings;
        the rows in ``announcements`` are only a projection of the YAML file.
        Pending runs for a changed announcement are discarded so the worker can
        materialize them again with the new template and lead time.
        """
        async with self.sessions.begin() as session:
            settings = await session.get(ApplicationSettings, 1)
            if settings is None:
                raise RuntimeError("Application settings have not been initialized")
            if settings.timezone != schedule.timezone:
                settings.timezone = schedule.timezone
                settings.updated_at = datetime.now(UTC)

            rows = list(await session.scalars(select(Announcement)))
            existing = {self._announcement_identity(row): row for row in rows}
            projected: list[Announcement] = []
            now = datetime.now(UTC)

            for configured in schedule.announcements:
                row = existing.pop(configured.identity, None)
                if row is None:
                    row = Announcement(
                        kind=configured.kind,
                        enabled=configured.enabled,
                        minute_of_day=configured.minute_of_day,
                        run_at_utc=configured.run_at_utc,
                        template=configured.template,
                        lead_seconds=configured.lead_seconds,
                        revision=1,
                    )
                    session.add(row)
                elif self._announcement_changed(row, configured):
                    await session.execute(
                        delete(AnnouncementRun).where(
                            AnnouncementRun.announcement_id == row.id,
                            AnnouncementRun.status.in_(CANCELLABLE_STATUSES),
                        )
                    )
                    row.enabled = configured.enabled
                    row.minute_of_day = configured.minute_of_day
                    row.run_at_utc = configured.run_at_utc
                    row.template = configured.template
                    row.lead_seconds = configured.lead_seconds
                    row.revision += 1
                    row.updated_at = now
                projected.append(row)

            for row in existing.values():
                await session.execute(
                    update(AnnouncementRun)
                    .where(
                        AnnouncementRun.announcement_id == row.id,
                        AnnouncementRun.status.in_(CANCELLABLE_STATUSES),
                    )
                    .values(
                        status="cancelled",
                        outcome_reason="announcement removed from schedule",
                        updated_at=now,
                        finished_at=now,
                    )
                )
                await session.delete(row)

            await session.flush()
            return [self._announcement_snapshot(row) for row in projected]

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

    async def get_announcement(self, announcement_id: int) -> AnnouncementSnapshot:
        async with self.sessions() as session:
            row = await session.get(Announcement, announcement_id)
            if row is None:
                raise AnnouncementNotFoundError(f"Announcement {announcement_id} does not exist")
            return self._announcement_snapshot(row)

    async def create_daily_announcement(
        self,
        *,
        minute_of_day: int,
        template: str,
        enabled: bool,
        lead_seconds: int,
    ) -> AnnouncementSnapshot:
        return await self._create_announcement(
            kind="daily",
            minute_of_day=minute_of_day,
            run_at_utc=None,
            template=template,
            enabled=enabled,
            lead_seconds=lead_seconds,
        )

    async def create_one_off_announcement(
        self,
        *,
        run_at_utc: datetime,
        template: str,
        enabled: bool,
        lead_seconds: int,
    ) -> AnnouncementSnapshot:
        return await self._create_announcement(
            kind="one_off",
            minute_of_day=None,
            run_at_utc=run_at_utc,
            template=template,
            enabled=enabled,
            lead_seconds=lead_seconds,
        )

    async def update_announcement(
        self,
        announcement_id: int,
        *,
        expected_revision: int,
        enabled: bool | None = None,
        minute_of_day: int | None = None,
        run_at_utc: datetime | None = None,
        template: str | None = None,
        lead_seconds: int | None = None,
    ) -> AnnouncementSnapshot:
        try:
            async with self.sessions.begin() as session:
                current = await session.get(Announcement, announcement_id)
                if current is None:
                    raise AnnouncementNotFoundError(
                        f"Announcement {announcement_id} does not exist"
                    )
                if current.revision != expected_revision:
                    raise AnnouncementRevisionConflictError(
                        f"Announcement {announcement_id} has revision {current.revision}, "
                        f"not {expected_revision}"
                    )
                if current.kind == "daily" and run_at_utc is not None:
                    raise AnnouncementKindMismatchError(
                        "run_at can only be changed on one-off announcements"
                    )
                if current.kind == "one_off" and minute_of_day is not None:
                    raise AnnouncementKindMismatchError(
                        "time can only be changed on daily announcements"
                    )

                values: dict = {
                    "revision": Announcement.revision + 1,
                    "updated_at": datetime.now(UTC),
                }
                if enabled is not None:
                    values["enabled"] = enabled
                if minute_of_day is not None:
                    values["minute_of_day"] = minute_of_day
                if run_at_utc is not None:
                    values["run_at_utc"] = run_at_utc
                if template is not None:
                    values["template"] = template
                if lead_seconds is not None:
                    values["lead_seconds"] = lead_seconds

                result = await session.execute(
                    update(Announcement)
                    .where(
                        Announcement.id == announcement_id,
                        Announcement.revision == expected_revision,
                    )
                    .values(**values)
                    .returning(Announcement)
                )
                row = result.scalar_one_or_none()
                if row is None:
                    raise AnnouncementRevisionConflictError(
                        f"Announcement {announcement_id} changed during the update"
                    )
                return self._announcement_snapshot(row)
        except IntegrityError as error:
            if self._is_duplicate_daily_time(error):
                raise DuplicateDailyTimeError(
                    "A daily announcement already exists at that time"
                ) from error
            raise

    async def delete_announcement(self, announcement_id: int, expected_revision: int) -> None:
        async with self.sessions.begin() as session:
            current = await session.get(Announcement, announcement_id)
            if current is None:
                raise AnnouncementNotFoundError(f"Announcement {announcement_id} does not exist")
            if current.revision != expected_revision:
                raise AnnouncementRevisionConflictError(
                    f"Announcement {announcement_id} has revision {current.revision}, "
                    f"not {expected_revision}"
                )
            now = datetime.now(UTC)
            await session.execute(
                update(AnnouncementRun)
                .where(
                    AnnouncementRun.announcement_id == announcement_id,
                    AnnouncementRun.status.in_(CANCELLABLE_STATUSES),
                )
                .values(
                    status="cancelled",
                    outcome_reason="announcement deleted",
                    updated_at=now,
                    finished_at=now,
                )
            )
            result = await session.execute(
                delete(Announcement)
                .where(
                    Announcement.id == announcement_id,
                    Announcement.revision == expected_revision,
                )
                .returning(Announcement.id)
            )
            if result.scalar_one_or_none() is None:
                raise AnnouncementRevisionConflictError(
                    f"Announcement {announcement_id} changed during deletion"
                )

    async def _create_announcement(
        self,
        *,
        kind: str,
        minute_of_day: int | None,
        run_at_utc: datetime | None,
        template: str,
        enabled: bool,
        lead_seconds: int,
    ) -> AnnouncementSnapshot:
        try:
            async with self.sessions.begin() as session:
                row = Announcement(
                    kind=kind,
                    minute_of_day=minute_of_day,
                    run_at_utc=run_at_utc,
                    template=template,
                    enabled=enabled,
                    lead_seconds=lead_seconds,
                    revision=1,
                )
                session.add(row)
                await session.flush()
                return self._announcement_snapshot(row)
        except IntegrityError as error:
            if self._is_duplicate_daily_time(error):
                raise DuplicateDailyTimeError(
                    "A daily announcement already exists at that time"
                ) from error
            raise

    @staticmethod
    def _is_duplicate_daily_time(error: IntegrityError) -> bool:
        return "announcements.minute_of_day" in str(error.orig)

    @classmethod
    def _announcement_identity(cls, row: Announcement) -> tuple[str, int | datetime]:
        if row.kind == "daily":
            assert row.minute_of_day is not None
            return row.kind, row.minute_of_day
        assert row.run_at_utc is not None
        return row.kind, cls._as_utc(row.run_at_utc)

    @classmethod
    def _announcement_changed(
        cls,
        row: Announcement,
        configured: "ScheduleAnnouncement",
    ) -> bool:
        run_at = cls._as_utc(row.run_at_utc) if row.run_at_utc is not None else None
        return (
            row.kind != configured.kind
            or row.enabled != configured.enabled
            or row.minute_of_day != configured.minute_of_day
            or run_at != configured.run_at_utc
            or row.template != configured.template
            or row.lead_seconds != configured.lead_seconds
        )

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
