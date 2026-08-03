import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from donnietts.database import Database
from donnietts.settings import ControllerSettings, SpeechSettings
from donnietts.worker import AnnouncementWorker


MORNING = datetime(2026, 1, 2, 8, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now_value = now

    def __call__(self) -> datetime:
        return self.now_value

    def advance(self, delta: timedelta) -> None:
        self.now_value += delta


def speech_settings() -> SpeechSettings:
    return SpeechSettings(
        base_url="http://speech.invalid/v1",
        api_key="test",
        model="test-model",
        voice="test-voice",
        instructions=None,
        generation_timeout_seconds=5,
        health_url=None,
        status_timeout_seconds=0.1,
    )


def speech_transport(*, status_code: int = 200) -> httpx.MockTransport:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/audio/speech":
            return httpx.Response(status_code, content=b"RIFF-fake-wav")
        return httpx.Response(404)

    return httpx.MockTransport(handler)


async def make_worker(
    database: Database,
    clock: FakeClock,
    transport: httpx.AsyncBaseTransport,
    *,
    audio_dir: Path,
    poll_interval_seconds: float = 30.0,
) -> tuple[AnnouncementWorker, list[str]]:
    played: list[str] = []

    async def record_playback(path: str) -> None:
        played.append(path)

    worker = AnnouncementWorker(
        database,
        speech_settings=speech_settings(),
        http_client=httpx.AsyncClient(transport=transport),
        audio_dir=audio_dir,
        playback=record_playback,
        poll_interval_seconds=poll_interval_seconds,
        now_provider=clock,
    )
    return worker, played


async def utc_database(initialized_settings: ControllerSettings) -> Database:
    database = Database(initialized_settings)
    await database.update_application_settings(timezone="UTC")
    return database


def test_worker_generates_and_plays_a_daily_announcement(
    initialized_settings: ControllerSettings,
) -> None:
    async def exercise() -> None:
        clock = FakeClock(MORNING - timedelta(minutes=5))
        database = await utc_database(initialized_settings)
        try:
            await database.create_daily_announcement(
                minute_of_day=8 * 60,
                template="It is {time}.",
                enabled=True,
                lead_seconds=300,
            )
            worker, played = await make_worker(
                database,
                clock,
                speech_transport(),
                audio_dir=initialized_settings.audio_dir,
            )
            await worker.reconcile()

            runs = await database.runs.list_all()
            assert len(runs) == 1
            run = runs[0]
            assert run.status == "ready"
            assert run.rendered_text == "It is eight o'clock A M."
            assert run.audio_path is not None
            assert Path(run.audio_path).read_bytes() == b"RIFF-fake-wav"

            clock.advance(timedelta(minutes=5, seconds=5))
            await worker.reconcile()

            current = await database.runs.get(run.id)
            assert current.status == "completed"
            assert current.finished_at is not None
            assert played == [run.audio_path]
        finally:
            await database.close()

    asyncio.run(exercise())


def test_worker_plays_a_one_off_announcement_at_its_deadlines(
    initialized_settings: ControllerSettings,
) -> None:
    async def exercise() -> None:
        clock = FakeClock(datetime(2026, 1, 2, 13, 50, tzinfo=UTC))
        database = await utc_database(initialized_settings)
        try:
            await database.create_one_off_announcement(
                run_at_utc=datetime(2026, 1, 2, 14, 0, tzinfo=UTC),
                template="It is {time}.",
                enabled=True,
                lead_seconds=300,
            )
            worker, played = await make_worker(
                database,
                clock,
                speech_transport(),
                audio_dir=initialized_settings.audio_dir,
            )

            # Materialized but not yet due for generation.
            await worker.reconcile()
            run = (await database.runs.list_all())[0]
            assert run.status == "planned"

            # Generation becomes due at scheduled - lead.
            clock.advance(timedelta(minutes=5))
            await worker.reconcile()
            run = await database.runs.get(run.id)
            assert run.status == "ready"
            assert run.rendered_text == "It is two o'clock P M."

            # Playback happens at the scheduled time.
            clock.advance(timedelta(minutes=5, seconds=5))
            await worker.reconcile()
            assert (await database.runs.get(run.id)).status == "completed"
            assert played == [run.audio_path]
        finally:
            await database.close()

    asyncio.run(exercise())


def test_worker_skips_due_runs_while_announcements_are_paused(
    initialized_settings: ControllerSettings,
) -> None:
    async def exercise() -> None:
        clock = FakeClock(MORNING - timedelta(minutes=5))
        database = await utc_database(initialized_settings)
        try:
            await database.update_application_settings(announcements_enabled=False)
            await database.create_daily_announcement(
                minute_of_day=8 * 60,
                template="It is {time}.",
                enabled=True,
                lead_seconds=300,
            )
            worker, played = await make_worker(
                database,
                clock,
                speech_transport(),
                audio_dir=initialized_settings.audio_dir,
            )
            await worker.reconcile()

            run = (await database.runs.list_all())[0]
            assert run.status == "skipped"
            assert run.outcome_reason == "announcements paused"
            assert played == []
        finally:
            await database.close()

    asyncio.run(exercise())


def test_worker_interrupts_stale_playback(
    initialized_settings: ControllerSettings,
) -> None:
    async def exercise() -> None:
        clock = FakeClock(MORNING - timedelta(minutes=5))
        database = await utc_database(initialized_settings)
        try:
            await database.create_daily_announcement(
                minute_of_day=8 * 60,
                template="It is {time}.",
                enabled=True,
                lead_seconds=300,
            )
            worker, _ = await make_worker(
                database,
                clock,
                speech_transport(),
                audio_dir=initialized_settings.audio_dir,
            )
            await worker.reconcile()

            run = (await database.runs.list_all())[0]
            await database.runs.transition(
                run.id,
                expected_status="ready",
                new_status="playing",
                now=clock(),
            )

            # Beyond the stale window (default 5 minutes), the run is
            # recovered as interrupted even though the worker never stopped.
            clock.advance(timedelta(minutes=10))
            await worker.reconcile()

            current = await database.runs.get(run.id)
            assert current.status == "interrupted"
            assert current.outcome_reason == "stale playback"
        finally:
            await database.close()

    asyncio.run(exercise())


def test_worker_retries_generation_and_skips_once_schedule_passes(
    initialized_settings: ControllerSettings,
) -> None:
    async def exercise() -> None:
        clock = FakeClock(MORNING - timedelta(minutes=5))
        database = await utc_database(initialized_settings)
        try:
            await database.create_daily_announcement(
                minute_of_day=8 * 60,
                template="It is {time}.",
                enabled=True,
                lead_seconds=300,
            )
            worker, _ = await make_worker(
                database,
                clock,
                speech_transport(status_code=500),
                audio_dir=initialized_settings.audio_dir,
            )

            # Generation fails; the run stays planned for a later retry.
            await worker.reconcile()
            run = (await database.runs.list_all())[0]
            assert run.status == "planned"

            # Once the scheduled time passes, the run is skipped instead of
            # generating stale audio.
            clock.advance(timedelta(minutes=11))
            await worker.reconcile()
            current = await database.runs.get(run.id)
            assert current.status == "skipped"
            assert current.outcome_reason == "missed schedule before generation"
        finally:
            await database.close()

    asyncio.run(exercise())


def test_worker_skips_a_ready_run_played_too_late(
    initialized_settings: ControllerSettings,
) -> None:
    async def exercise() -> None:
        clock = FakeClock(MORNING - timedelta(minutes=5))
        database = await utc_database(initialized_settings)
        try:
            await database.create_daily_announcement(
                minute_of_day=8 * 60,
                template="It is {time}.",
                enabled=True,
                lead_seconds=300,
            )
            worker, played = await make_worker(
                database,
                clock,
                speech_transport(),
                audio_dir=initialized_settings.audio_dir,
            )
            await worker.reconcile()
            run = (await database.runs.list_all())[0]
            assert run.status == "ready"

            # Longer than the 120s late-playback grace period.
            clock.advance(timedelta(minutes=10))
            await worker.reconcile()

            current = await database.runs.get(run.id)
            assert current.status == "skipped"
            assert current.outcome_reason == "missed playback window"
            assert played == []
        finally:
            await database.close()

    asyncio.run(exercise())


def test_worker_materializes_each_occurrence_only_once(
    initialized_settings: ControllerSettings,
) -> None:
    async def exercise() -> None:
        clock = FakeClock(MORNING - timedelta(minutes=5))
        database = await utc_database(initialized_settings)
        try:
            await database.create_daily_announcement(
                minute_of_day=8 * 60,
                template="It is {time}.",
                enabled=True,
                lead_seconds=300,
            )
            worker, _ = await make_worker(
                database,
                clock,
                speech_transport(),
                audio_dir=initialized_settings.audio_dir,
            )

            await worker.reconcile()
            await worker.reconcile()

            assert len(await database.runs.list_all()) == 1
        finally:
            await database.close()

    asyncio.run(exercise())
