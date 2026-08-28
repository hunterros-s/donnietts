"""Scheduler worker that materializes and executes durable announcement runs."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from donnietts.announcement_runs import (
    AnnouncementRunNotFoundError,
    AnnouncementRunRepository,
    AnnouncementRunSnapshot,
    DuplicateAnnouncementRunError,
    InvalidRunDataError,
    InvalidRunTransitionError,
    RunStateConflictError,
)
from donnietts.audio import play_wav_file
from donnietts.context import CONTEXT_SETTINGS, ContextSettings
from donnietts.database import ApplicationSettingsSnapshot, Database
from donnietts.rendering import render_template
from donnietts.schedule import ScheduleError, ScheduleStore
from donnietts.settings import ControllerSettings, SpeechSettings
from donnietts.speech_client import OpenAICompatibleSpeechClient


logger = logging.getLogger(__name__)

Playback = Callable[[str], Awaitable[None]]
NowProvider = Callable[[], datetime]


async def _playback(path: str) -> None:
    await asyncio.to_thread(play_wav_file, path)


class AnnouncementWorker:
    """Materializes planned runs, generates speech, and plays announcements.

    Each call to :meth:`reconcile` performs one scheduling pass against the
    current time. The worker is restart-safe: speech generation is retried
    until the scheduled time passes (the run stays ``planned``), and runs that
    were mid-playback when the process stopped are recovered as
    ``interrupted`` once they go stale.
    """

    def __init__(
        self,
        database: Database,
        *,
        speech_settings: SpeechSettings,
        http_client: httpx.AsyncClient,
        audio_dir: Path,
        context_settings: ContextSettings = CONTEXT_SETTINGS,
        playback: Playback = _playback,
        stale_after_seconds: float = 300.0,
        play_late_grace_seconds: float = 120.0,
        poll_interval_seconds: float = 30.0,
        now_provider: NowProvider | None = None,
        schedule_store: ScheduleStore | None = None,
    ):
        self.database = database
        self.speech_client = OpenAICompatibleSpeechClient(http_client, speech_settings)
        self.http_client = http_client
        self.audio_dir = audio_dir
        self.context_settings = context_settings
        self.playback = playback
        self.stale_after_seconds = stale_after_seconds
        self.play_late_grace_seconds = play_late_grace_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self._now = now_provider or (lambda: datetime.now(UTC))
        self.schedule_store = schedule_store

    @property
    def runs(self) -> AnnouncementRunRepository:
        return self.database.runs

    def now(self) -> datetime:
        return self._now()

    async def reconcile(self) -> None:
        """Perform one scheduling pass: recover, materialize, process."""
        now = self.now()
        await self._recover_stale_runs(now)
        if self.schedule_store is not None:
            try:
                schedule = await asyncio.to_thread(self.schedule_store.load)
            except ScheduleError as error:
                logger.warning("Keeping last valid schedule: %s", error)
            else:
                await self.database.sync_schedule(schedule)
        application_settings = await self.database.get_application_settings()
        await self._materialize_runs(now, application_settings)
        await self._process_due_runs(now, application_settings)

    async def run(self) -> None:
        """Run the scheduling loop until cancelled."""
        logger.info(
            "Announcement worker started: speech=%s model=%s voice=%s "
            "audio_dir=%s poll=%ss",
            self.speech_client.settings.base_url,
            self.speech_client.settings.model,
            self.speech_client.settings.voice,
            self.audio_dir,
            self.poll_interval_seconds,
        )
        while True:
            try:
                await self.reconcile()
            except Exception:
                logger.exception("Announcement worker reconcile failed")
            await self._sleep_until_next()

    async def _sleep_until_next(self) -> None:
        now = self.now()
        deadline = now + timedelta(seconds=self.poll_interval_seconds)
        try:
            for run in await self.runs.list_all():
                if run.status == "planned" and run.generation_due_at_utc > now:
                    deadline = min(deadline, run.generation_due_at_utc)
                elif run.status == "ready" and run.scheduled_for_utc > now:
                    deadline = min(deadline, run.scheduled_for_utc)
        except Exception:
            logger.exception("Could not compute next scheduling deadline")
            deadline = now + timedelta(seconds=self.poll_interval_seconds)
        await asyncio.sleep(max((deadline - now).total_seconds(), 0.0))

    async def _recover_stale_runs(self, now: datetime) -> None:
        stale_before = now - timedelta(seconds=self.stale_after_seconds)
        for run in await self.runs.list_stale_in_progress(stale_before):
            logger.warning("Interrupting stale run %s", run.id)
            await self._transition(
                run.id,
                expected_status="playing",
                new_status="interrupted",
                reason="stale playback",
            )

    async def _materialize_runs(
        self,
        now: datetime,
        settings: ApplicationSettingsSnapshot,
    ) -> None:
        timezone = ZoneInfo(settings.timezone)
        for announcement in await self.database.list_announcements():
            if not announcement.enabled:
                continue

            if announcement.kind == "daily":
                scheduled_for = self._next_daily_occurrence(
                    announcement.minute_of_day,
                    now,
                    timezone,
                )
            else:
                if announcement.run_at_utc is None or announcement.run_at_utc <= now:
                    continue
                scheduled_for = announcement.run_at_utc

            generation_due = max(
                scheduled_for - timedelta(seconds=announcement.lead_seconds),
                now,
            )
            try:
                await self.runs.create_planned(
                    announcement.id,
                    scheduled_for_utc=scheduled_for,
                    generation_due_at_utc=generation_due,
                )
            except DuplicateAnnouncementRunError:
                pass
            except Exception:
                logger.exception(
                    "Could not materialize run for announcement %s",
                    announcement.id,
                )

    @staticmethod
    def _next_daily_occurrence(
        minute_of_day: int,
        now: datetime,
        timezone: ZoneInfo,
    ) -> datetime:
        now_local = now.astimezone(timezone)
        scheduled_local = now_local.replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + timedelta(minutes=minute_of_day)
        if scheduled_local <= now_local:
            scheduled_local += timedelta(days=1)
        return scheduled_local.astimezone(UTC)

    async def _process_due_runs(
        self,
        now: datetime,
        settings: ApplicationSettingsSnapshot,
    ) -> None:
        if not settings.announcements_enabled:
            due_runs = await self.runs.list_due_generation(now)
            due_runs += await self.runs.list_due_playback(now)
            for run in due_runs:
                logger.info("Skipping run %s: announcements paused", run.id)
                await self._transition(
                    run.id,
                    expected_status=run.status,
                    new_status="skipped",
                    reason="announcements paused",
                )
            return

        timezone = ZoneInfo(settings.timezone)
        for run in await self.runs.list_due_generation(now):
            if run.scheduled_for_utc <= now:
                await self._transition(
                    run.id,
                    expected_status="planned",
                    new_status="skipped",
                    reason="missed schedule before generation",
                )
                continue
            await self._generate_run(run, timezone)

        for run in await self.runs.list_due_playback(now):
            await self._play_run(run, now)

    async def _generate_run(
        self,
        run: AnnouncementRunSnapshot,
        timezone: ZoneInfo,
    ) -> None:
        render_now = run.scheduled_for_utc.astimezone(timezone)
        try:
            rendered = await render_template(
                self.http_client,
                run.template_snapshot,
                render_now,
                self.context_settings,
            )
            wav = await self.speech_client.generate_wav(rendered)
            audio_path = await self._write_audio(run.id, wav)
            await self._transition(
                run.id,
                expected_status="planned",
                new_status="ready",
                rendered_text=rendered,
                audio_path=str(audio_path),
            )
            logger.info(
                "Generated run %s (announcement %s) scheduled %s",
                run.id,
                run.announcement_id,
                run.scheduled_for_utc.isoformat(),
            )
        except Exception as error:
            # Leave the run planned; generation is retried on later passes
            # until the scheduled time passes.
            logger.warning("Could not generate run %s: %s", run.id, error)

    async def _play_run(self, run: AnnouncementRunSnapshot, now: datetime) -> None:
        if run.audio_path is None:
            await self._transition(
                run.id,
                expected_status="ready",
                new_status="failed",
                error="ready run has no audio",
            )
            return
        if now > run.scheduled_for_utc + timedelta(seconds=self.play_late_grace_seconds):
            await self._transition(
                run.id,
                expected_status="ready",
                new_status="skipped",
                reason="missed playback window",
            )
            return

        try:
            await self._transition(run.id, expected_status="ready", new_status="playing")
            await self.playback(run.audio_path)
            await self._transition(run.id, expected_status="playing", new_status="completed")
            logger.info("Completed run %s", run.id)
        except Exception as error:
            logger.warning("Playback failed for run %s: %s", run.id, error)
            await self._transition(
                run.id,
                expected_status="playing",
                new_status="failed",
                error=str(error),
            )

    async def _write_audio(self, run_id: int, wav: bytes) -> Path:
        path = self.audio_dir / f"run_{run_id}.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, wav)
        return path

    async def _transition(
        self,
        run_id: int,
        expected_status: str,
        new_status: str,
        *,
        rendered_text: str | None = None,
        audio_path: str | None = None,
        error: str | None = None,
        reason: str | None = None,
    ) -> None:
        try:
            await self.runs.transition(
                run_id,
                expected_status=expected_status,
                new_status=new_status,
                rendered_text=rendered_text,
                audio_path=audio_path,
                error=error,
                reason=reason,
                now=self.now(),
            )
        except (
            AnnouncementRunNotFoundError,
            RunStateConflictError,
            InvalidRunTransitionError,
            InvalidRunDataError,
        ) as exc:
            logger.warning("Could not transition run %s to %s: %s", run_id, new_status, exc)


async def run_worker(
    settings: ControllerSettings,
    *,
    poll_interval_seconds: float | None = None,
) -> None:
    """Wire a controller configuration to a worker and run it until cancelled."""
    database = Database(settings)
    try:
        await database.initialize()
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as http_client:
            worker = AnnouncementWorker(
                database,
                speech_settings=settings.speech,
                http_client=http_client,
                audio_dir=settings.audio_dir,
                poll_interval_seconds=(
                    poll_interval_seconds if poll_interval_seconds is not None else 30.0
                ),
                schedule_store=ScheduleStore(settings.resolved_schedule_path),
            )
            await worker.run()
    finally:
        await database.close()
