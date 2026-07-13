from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from donnietts.models import Announcement, AnnouncementRun


RunStatus = Literal[
    "planned",
    "ready",
    "playing",
    "completed",
    "failed",
    "skipped",
    "cancelled",
    "interrupted",
]

ALLOWED_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    "planned": frozenset({"ready", "failed", "skipped", "cancelled"}),
    "ready": frozenset({"playing", "failed", "skipped", "cancelled"}),
    "playing": frozenset({"completed", "failed", "interrupted"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "skipped": frozenset(),
    "cancelled": frozenset(),
    "interrupted": frozenset(),
}
IN_PROGRESS_STATUSES = frozenset({"playing"})
CANCELLABLE_STATUSES = frozenset({"planned", "ready"})
TERMINAL_STATUSES = frozenset({"completed", "failed", "skipped", "cancelled", "interrupted"})
REASON_STATUSES = frozenset({"skipped", "cancelled", "interrupted"})


class AnnouncementRunNotFoundError(RuntimeError):
    pass


class RunSourceNotFoundError(RuntimeError):
    pass


class DuplicateAnnouncementRunError(RuntimeError):
    pass


class RunStateConflictError(RuntimeError):
    pass


class InvalidRunTransitionError(ValueError):
    pass


class InvalidRunDataError(ValueError):
    pass


@dataclass(frozen=True)
class AnnouncementRunSnapshot:
    id: int
    announcement_id: int | None
    announcement_revision: int
    announcement_kind: str
    scheduled_for_utc: datetime
    generation_due_at_utc: datetime
    status: str
    template_snapshot: str
    rendered_text: str | None
    audio_path: str | None
    error: str | None
    outcome_reason: str | None
    created_at: datetime
    updated_at: datetime
    ready_at: datetime | None
    playback_started_at: datetime | None
    finished_at: datetime | None


class AnnouncementRunRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]):
        self.sessions = sessions

    async def create_planned(
        self,
        announcement_id: int,
        *,
        scheduled_for_utc: datetime,
        generation_due_at_utc: datetime,
    ) -> AnnouncementRunSnapshot:
        scheduled_for_utc = self._normalize_utc(scheduled_for_utc, "scheduled_for_utc")
        generation_due_at_utc = self._normalize_utc(
            generation_due_at_utc,
            "generation_due_at_utc",
        )
        if generation_due_at_utc > scheduled_for_utc:
            raise InvalidRunDataError(
                "generation_due_at_utc must not be later than scheduled_for_utc"
            )

        try:
            async with self.sessions.begin() as session:
                announcement = await session.get(Announcement, announcement_id)
                if announcement is None:
                    raise RunSourceNotFoundError(
                        f"Announcement {announcement_id} does not exist"
                    )
                row = AnnouncementRun(
                    announcement_id=announcement.id,
                    announcement_revision=announcement.revision,
                    announcement_kind=announcement.kind,
                    scheduled_for_utc=scheduled_for_utc,
                    generation_due_at_utc=generation_due_at_utc,
                    status="planned",
                    template_snapshot=announcement.template,
                )
                session.add(row)
                await session.flush()
                return self._snapshot(row)
        except IntegrityError as error:
            if self._is_duplicate_occurrence(error):
                raise DuplicateAnnouncementRunError(
                    f"Announcement {announcement_id} already has a run at "
                    f"{scheduled_for_utc.isoformat()}"
                ) from error
            raise

    async def get(self, run_id: int) -> AnnouncementRunSnapshot:
        async with self.sessions() as session:
            row = await session.get(AnnouncementRun, run_id)
            if row is None:
                raise AnnouncementRunNotFoundError(f"Announcement run {run_id} does not exist")
            return self._snapshot(row)

    async def list_all(self) -> list[AnnouncementRunSnapshot]:
        async with self.sessions() as session:
            rows = await session.scalars(
                select(AnnouncementRun).order_by(
                    AnnouncementRun.scheduled_for_utc,
                    AnnouncementRun.id,
                )
            )
            return [self._snapshot(row) for row in rows]

    async def list_stale_in_progress(
        self,
        stale_before_utc: datetime,
    ) -> list[AnnouncementRunSnapshot]:
        stale_before_utc = self._normalize_utc(stale_before_utc, "stale_before_utc")
        async with self.sessions() as session:
            rows = await session.scalars(
                select(AnnouncementRun)
                .where(
                    AnnouncementRun.status.in_(IN_PROGRESS_STATUSES),
                    AnnouncementRun.updated_at <= stale_before_utc,
                )
                .order_by(AnnouncementRun.updated_at, AnnouncementRun.id)
            )
            return [self._snapshot(row) for row in rows]

    async def transition(
        self,
        run_id: int,
        *,
        expected_status: RunStatus,
        new_status: RunStatus,
        rendered_text: str | None = None,
        audio_path: str | None = None,
        error: str | None = None,
        reason: str | None = None,
        now: datetime | None = None,
    ) -> AnnouncementRunSnapshot:
        now = self._normalize_utc(now or datetime.now(UTC), "now")
        values = self._transition_values(
            expected_status=expected_status,
            new_status=new_status,
            rendered_text=rendered_text,
            audio_path=audio_path,
            error=error,
            reason=reason,
            now=now,
        )

        async with self.sessions.begin() as session:
            result = await session.execute(
                update(AnnouncementRun)
                .where(
                    AnnouncementRun.id == run_id,
                    AnnouncementRun.status == expected_status,
                )
                .values(**values)
                .returning(AnnouncementRun)
            )
            row = result.scalar_one_or_none()
            if row is not None:
                return self._snapshot(row)

            actual_status = await session.scalar(
                select(AnnouncementRun.status).where(AnnouncementRun.id == run_id)
            )
            if actual_status is None:
                raise AnnouncementRunNotFoundError(f"Announcement run {run_id} does not exist")
            raise RunStateConflictError(
                f"Announcement run {run_id} has status {actual_status}, "
                f"not {expected_status}"
            )

    @staticmethod
    def _transition_values(
        *,
        expected_status: RunStatus,
        new_status: RunStatus,
        rendered_text: str | None,
        audio_path: str | None,
        error: str | None,
        reason: str | None,
        now: datetime,
    ) -> dict[str, object]:
        if expected_status not in ALLOWED_TRANSITIONS or new_status not in ALLOWED_TRANSITIONS:
            raise InvalidRunTransitionError("Unknown announcement run status")
        if new_status not in ALLOWED_TRANSITIONS[expected_status]:
            raise InvalidRunTransitionError(
                f"Announcement runs cannot transition from {expected_status} to {new_status}"
            )

        values: dict[str, object] = {"status": new_status, "updated_at": now}
        if new_status == "ready":
            rendered_text = AnnouncementRunRepository._required_text(
                rendered_text,
                "rendered_text",
            )
            audio_path = AnnouncementRunRepository._required_text(audio_path, "audio_path")
            values.update(
                rendered_text=rendered_text,
                audio_path=audio_path,
                ready_at=now,
            )
        elif new_status == "playing":
            values["playback_started_at"] = now

        if new_status == "failed":
            values["error"] = AnnouncementRunRepository._required_text(error, "error")
        elif error is not None:
            raise InvalidRunDataError("error can only be supplied for a failed run")

        if new_status in REASON_STATUSES:
            values["outcome_reason"] = AnnouncementRunRepository._required_text(
                reason,
                "reason",
            )
        elif reason is not None:
            raise InvalidRunDataError(
                "reason can only be supplied for a skipped, cancelled, or interrupted run"
            )

        if new_status != "ready" and (rendered_text is not None or audio_path is not None):
            raise InvalidRunDataError(
                "rendered_text and audio_path can only be supplied when a run becomes ready"
            )

        if new_status in TERMINAL_STATUSES:
            values["finished_at"] = now
        return values

    @staticmethod
    def _required_text(value: str | None, name: str) -> str:
        normalized = value.strip() if value is not None else ""
        if not normalized:
            raise InvalidRunDataError(f"{name} must not be empty")
        return normalized

    @staticmethod
    def _normalize_utc(value: datetime, name: str) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise InvalidRunDataError(f"{name} must include a UTC offset")
        return value.astimezone(UTC)

    @staticmethod
    def _is_duplicate_occurrence(error: IntegrityError) -> bool:
        message = str(error.orig)
        return (
            "announcement_runs.announcement_id" in message
            and "announcement_runs.scheduled_for_utc" in message
        )

    @classmethod
    def _snapshot(cls, row: AnnouncementRun) -> AnnouncementRunSnapshot:
        return AnnouncementRunSnapshot(
            id=row.id,
            announcement_id=row.announcement_id,
            announcement_revision=row.announcement_revision,
            announcement_kind=row.announcement_kind,
            scheduled_for_utc=cls._as_utc(row.scheduled_for_utc),
            generation_due_at_utc=cls._as_utc(row.generation_due_at_utc),
            status=row.status,
            template_snapshot=row.template_snapshot,
            rendered_text=row.rendered_text,
            audio_path=row.audio_path,
            error=row.error,
            outcome_reason=row.outcome_reason,
            created_at=cls._as_utc(row.created_at),
            updated_at=cls._as_utc(row.updated_at),
            ready_at=cls._optional_utc(row.ready_at),
            playback_started_at=cls._optional_utc(row.playback_started_at),
            finished_at=cls._optional_utc(row.finished_at),
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is not None:
            return value.astimezone(UTC)
        return value.replace(tzinfo=UTC)

    @classmethod
    def _optional_utc(cls, value: datetime | None) -> datetime | None:
        return cls._as_utc(value) if value is not None else None
