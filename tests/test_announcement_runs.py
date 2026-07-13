import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from donnietts.announcement_runs import (
    AnnouncementRunNotFoundError,
    AnnouncementRunSnapshot,
    DuplicateAnnouncementRunError,
    InvalidRunDataError,
    InvalidRunTransitionError,
    RunSourceNotFoundError,
    RunStateConflictError,
)
from donnietts.database import Database
from donnietts.settings import ControllerSettings


SCHEDULED = datetime(2100, 1, 2, 15, 0, tzinfo=UTC)
GENERATION_DUE = SCHEDULED - timedelta(minutes=5)


async def create_source(database: Database, minute_of_day: int = 7 * 60 + 30):
    return await database.create_daily_announcement(
        minute_of_day=minute_of_day,
        template="It is {time}.",
        enabled=True,
        lead_seconds=300,
    )


async def create_run(
    database: Database,
    *,
    minute_of_day: int = 7 * 60 + 30,
    scheduled_for_utc: datetime = SCHEDULED,
) -> AnnouncementRunSnapshot:
    source = await create_source(database, minute_of_day)
    return await database.runs.create_planned(
        source.id,
        scheduled_for_utc=scheduled_for_utc,
        generation_due_at_utc=scheduled_for_utc - timedelta(minutes=5),
    )


def test_planned_run_snapshots_its_source_and_rejects_duplicates(
    migrated_settings: ControllerSettings,
) -> None:
    async def exercise() -> None:
        database = Database(migrated_settings)
        try:
            source = await create_source(database)
            scheduled_with_offset = datetime.fromisoformat("2100-01-02T10:00:00-05:00")
            due_with_offset = datetime.fromisoformat("2100-01-02T09:55:00-05:00")
            run = await database.runs.create_planned(
                source.id,
                scheduled_for_utc=scheduled_with_offset,
                generation_due_at_utc=due_with_offset,
            )

            assert run.announcement_id == source.id
            assert run.announcement_revision == 1
            assert run.announcement_kind == "daily"
            assert run.scheduled_for_utc == SCHEDULED
            assert run.generation_due_at_utc == GENERATION_DUE
            assert run.status == "planned"
            assert run.template_snapshot == "It is {time}."
            assert run.attempt_count == 0
            assert run.rendered_text is None
            assert run.audio_path is None
            assert run.finished_at is None

            with pytest.raises(DuplicateAnnouncementRunError):
                await database.runs.create_planned(
                    source.id,
                    scheduled_for_utc=SCHEDULED,
                    generation_due_at_utc=GENERATION_DUE,
                )
            assert len(await database.runs.list_all()) == 1
        finally:
            await database.close()

    asyncio.run(exercise())


def test_run_creation_validates_source_and_times(migrated_settings: ControllerSettings) -> None:
    async def exercise() -> None:
        database = Database(migrated_settings)
        try:
            source = await create_source(database)
            with pytest.raises(RunSourceNotFoundError):
                await database.runs.create_planned(
                    999_999,
                    scheduled_for_utc=SCHEDULED,
                    generation_due_at_utc=GENERATION_DUE,
                )
            with pytest.raises(InvalidRunDataError, match="UTC offset"):
                await database.runs.create_planned(
                    source.id,
                    scheduled_for_utc=SCHEDULED.replace(tzinfo=None),
                    generation_due_at_utc=GENERATION_DUE,
                )
            with pytest.raises(InvalidRunDataError, match="must not be later"):
                await database.runs.create_planned(
                    source.id,
                    scheduled_for_utc=SCHEDULED,
                    generation_due_at_utc=SCHEDULED + timedelta(seconds=1),
                )
        finally:
            await database.close()

    asyncio.run(exercise())


def test_run_preserves_snapshots_after_source_edit_and_delete(
    migrated_settings: ControllerSettings,
) -> None:
    async def exercise() -> None:
        database = Database(migrated_settings)
        try:
            source = await create_source(database)
            run = await database.runs.create_planned(
                source.id,
                scheduled_for_utc=SCHEDULED,
                generation_due_at_utc=GENERATION_DUE,
            )
            updated_source = await database.update_announcement(
                source.id,
                expected_revision=1,
                template="Updated template",
            )
            await database.delete_announcement(source.id, updated_source.revision)

            preserved = await database.runs.get(run.id)
            assert preserved.announcement_id is None
            assert preserved.announcement_revision == 1
            assert preserved.announcement_kind == "daily"
            assert preserved.template_snapshot == "It is {time}."
            assert preserved.status == "cancelled"
            assert preserved.outcome_reason == "announcement deleted"
            assert preserved.finished_at is not None
        finally:
            await database.close()

    asyncio.run(exercise())


def test_run_happy_path_records_state_timestamps(migrated_settings: ControllerSettings) -> None:
    async def exercise() -> None:
        database = Database(migrated_settings)
        try:
            planned = await create_run(database)
            generation_started = GENERATION_DUE
            ready_at = generation_started + timedelta(seconds=2)
            playback_started = SCHEDULED
            completed_at = playback_started + timedelta(seconds=4)

            generating = await database.runs.transition(
                planned.id,
                expected_status="planned",
                new_status="generating",
                now=generation_started,
            )
            assert generating.status == "generating"
            assert generating.attempt_count == 1
            assert generating.generation_started_at == generation_started

            ready = await database.runs.transition(
                planned.id,
                expected_status="generating",
                new_status="ready",
                rendered_text="It is three PM.",
                audio_path=" /tmp/run.wav ",
                now=ready_at,
            )
            assert ready.status == "ready"
            assert ready.rendered_text == "It is three PM."
            assert ready.audio_path == "/tmp/run.wav"
            assert ready.ready_at == ready_at

            playing = await database.runs.transition(
                planned.id,
                expected_status="ready",
                new_status="playing",
                now=playback_started,
            )
            assert playing.status == "playing"
            assert playing.playback_started_at == playback_started

            completed = await database.runs.transition(
                planned.id,
                expected_status="playing",
                new_status="completed",
                now=completed_at,
            )
            assert completed.status == "completed"
            assert completed.finished_at == completed_at
            assert completed.error is None
            assert completed.outcome_reason is None

            assert completed.announcement_id is not None
            await database.delete_announcement(completed.announcement_id, expected_revision=1)
            preserved = await database.runs.get(completed.id)
            assert preserved.announcement_id is None
            assert preserved.status == "completed"
            assert preserved.finished_at == completed_at
        finally:
            await database.close()

    asyncio.run(exercise())


def test_invalid_and_conflicting_transitions_are_rejected(
    migrated_settings: ControllerSettings,
) -> None:
    async def exercise() -> None:
        database = Database(migrated_settings)
        try:
            planned = await create_run(database)
            with pytest.raises(InvalidRunTransitionError):
                await database.runs.transition(
                    planned.id,
                    expected_status="planned",
                    new_status="ready",
                    rendered_text="Rendered",
                    audio_path="/tmp/run.wav",
                )
            with pytest.raises(InvalidRunDataError, match="reason"):
                await database.runs.transition(
                    planned.id,
                    expected_status="planned",
                    new_status="skipped",
                )

            skipped = await database.runs.transition(
                planned.id,
                expected_status="planned",
                new_status="skipped",
                reason=" global pause ",
            )
            assert skipped.outcome_reason == "global pause"
            assert skipped.finished_at is not None

            with pytest.raises(RunStateConflictError):
                await database.runs.transition(
                    planned.id,
                    expected_status="planned",
                    new_status="generating",
                )
            with pytest.raises(InvalidRunTransitionError):
                await database.runs.transition(
                    planned.id,
                    expected_status="skipped",
                    new_status="generating",
                )
            with pytest.raises(AnnouncementRunNotFoundError):
                await database.runs.transition(
                    999_999,
                    expected_status="planned",
                    new_status="generating",
                )
            assert (await database.runs.get(planned.id)).status == "skipped"
        finally:
            await database.close()

    asyncio.run(exercise())


def test_ready_and_failed_transitions_require_outputs(
    migrated_settings: ControllerSettings,
) -> None:
    async def exercise() -> None:
        database = Database(migrated_settings)
        try:
            run = await create_run(database)
            await database.runs.transition(
                run.id,
                expected_status="planned",
                new_status="generating",
            )
            with pytest.raises(InvalidRunDataError, match="audio_path"):
                await database.runs.transition(
                    run.id,
                    expected_status="generating",
                    new_status="ready",
                    rendered_text="Rendered text",
                )
            with pytest.raises(InvalidRunDataError, match="error"):
                await database.runs.transition(
                    run.id,
                    expected_status="generating",
                    new_status="failed",
                )

            failed = await database.runs.transition(
                run.id,
                expected_status="generating",
                new_status="failed",
                error=" speech provider unavailable ",
            )
            assert failed.error == "speech provider unavailable"
            assert failed.finished_at is not None
        finally:
            await database.close()

    asyncio.run(exercise())


def test_cancellation_and_interruption_record_reasons(
    migrated_settings: ControllerSettings,
) -> None:
    async def exercise() -> None:
        database = Database(migrated_settings)
        try:
            cancelled_run = await create_run(database, minute_of_day=7 * 60)
            cancelled = await database.runs.transition(
                cancelled_run.id,
                expected_status="planned",
                new_status="cancelled",
                reason=" announcement deleted ",
            )
            assert cancelled.outcome_reason == "announcement deleted"
            assert cancelled.finished_at is not None

            interrupted_run = await create_run(database, minute_of_day=7 * 60 + 1)
            await database.runs.transition(
                interrupted_run.id,
                expected_status="planned",
                new_status="generating",
            )
            await database.runs.transition(
                interrupted_run.id,
                expected_status="generating",
                new_status="ready",
                rendered_text="Rendered",
                audio_path="/tmp/interrupted.wav",
            )
            await database.runs.transition(
                interrupted_run.id,
                expected_status="ready",
                new_status="playing",
            )
            interrupted = await database.runs.transition(
                interrupted_run.id,
                expected_status="playing",
                new_status="interrupted",
                reason=" controller restarted ",
            )
            assert interrupted.outcome_reason == "controller restarted"
            assert interrupted.finished_at is not None
        finally:
            await database.close()

    asyncio.run(exercise())


def test_concurrent_run_claims_allow_only_one_worker(
    migrated_settings: ControllerSettings,
) -> None:
    async def exercise() -> tuple[list[AnnouncementRunSnapshot], list[Exception], int]:
        database = Database(migrated_settings)
        try:
            run = await create_run(database)
            results = await asyncio.gather(
                database.runs.transition(
                    run.id,
                    expected_status="planned",
                    new_status="generating",
                ),
                database.runs.transition(
                    run.id,
                    expected_status="planned",
                    new_status="generating",
                ),
                return_exceptions=True,
            )
            successes = [item for item in results if isinstance(item, AnnouncementRunSnapshot)]
            errors = [item for item in results if isinstance(item, Exception)]
            current = await database.runs.get(run.id)
            return successes, errors, current.attempt_count
        finally:
            await database.close()

    successes, errors, attempt_count = asyncio.run(exercise())

    assert len(successes) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], RunStateConflictError)
    assert attempt_count == 1


def test_stale_in_progress_query_supports_restart_recovery(
    migrated_settings: ControllerSettings,
) -> None:
    async def exercise() -> tuple[set[int], set[int], set[int]]:
        database = Database(migrated_settings)
        try:
            old_generating = await create_run(
                database,
                minute_of_day=7 * 60,
                scheduled_for_utc=SCHEDULED,
            )
            old_playing = await create_run(
                database,
                minute_of_day=7 * 60 + 1,
                scheduled_for_utc=SCHEDULED + timedelta(minutes=1),
            )
            recent_generating = await create_run(
                database,
                minute_of_day=7 * 60 + 2,
                scheduled_for_utc=SCHEDULED + timedelta(minutes=2),
            )
            planned = await create_run(
                database,
                minute_of_day=7 * 60 + 3,
                scheduled_for_utc=SCHEDULED + timedelta(minutes=3),
            )
            old_time = datetime(2099, 12, 31, 12, 0, tzinfo=UTC)
            recent_time = old_time + timedelta(hours=2)

            await database.runs.transition(
                old_generating.id,
                expected_status="planned",
                new_status="generating",
                now=old_time,
            )
            await database.runs.transition(
                old_playing.id,
                expected_status="planned",
                new_status="generating",
                now=old_time,
            )
            await database.runs.transition(
                old_playing.id,
                expected_status="generating",
                new_status="ready",
                rendered_text="Ready",
                audio_path="/tmp/ready.wav",
                now=old_time,
            )
            await database.runs.transition(
                old_playing.id,
                expected_status="ready",
                new_status="playing",
                now=old_time,
            )
            await database.runs.transition(
                recent_generating.id,
                expected_status="planned",
                new_status="generating",
                now=recent_time,
            )

            stale = await database.runs.list_stale_in_progress(
                old_time + timedelta(hours=1)
            )
            return (
                {run.id for run in stale},
                {old_generating.id, old_playing.id},
                {recent_generating.id, planned.id},
            )
        finally:
            await database.close()

    stale_ids, expected_stale_ids, excluded_ids = asyncio.run(exercise())

    assert stale_ids == expected_stale_ids
    assert stale_ids.isdisjoint(excluded_ids)
