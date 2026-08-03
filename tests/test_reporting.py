import asyncio
from datetime import UTC, datetime, timedelta

from donnietts.database import Database
from donnietts.reporting import runs_text, schedule_text
from donnietts.settings import ControllerSettings


def test_schedule_text_lists_announcements(
    initialized_settings: ControllerSettings,
) -> None:
    async def seed() -> None:
        database = Database(initialized_settings)
        try:
            await database.update_application_settings(timezone="UTC")
            await database.create_daily_announcement(
                minute_of_day=8 * 60,
                template="Good morning. It is {time}.",
                enabled=True,
                lead_seconds=300,
            )
        finally:
            await database.close()

    asyncio.run(seed())
    text = asyncio.run(schedule_text(initialized_settings))

    assert "Announcements are active" in text
    assert "timezone: UTC" in text
    assert "08:00" in text
    assert "daily" in text
    assert "yes" in text
    assert "Good morning. It is {time}." in text


def test_schedule_text_reports_paused_mode(
    initialized_settings: ControllerSettings,
) -> None:
    async def seed() -> None:
        database = Database(initialized_settings)
        try:
            await database.update_application_settings(announcements_enabled=False)
        finally:
            await database.close()

    asyncio.run(seed())
    assert "Announcements are paused" in asyncio.run(schedule_text(initialized_settings))


def test_schedule_text_reports_an_empty_schedule(
    initialized_settings: ControllerSettings,
) -> None:
    assert "No announcements configured." in asyncio.run(
        schedule_text(initialized_settings)
    )


def test_runs_text_lists_runs_newest_first(
    initialized_settings: ControllerSettings,
) -> None:
    async def seed() -> list[int]:
        database = Database(initialized_settings)
        try:
            run_ids = []
            for minute in (7 * 60, 8 * 60, 9 * 60):
                source = await database.create_daily_announcement(
                    minute_of_day=minute,
                    template="It is {time}.",
                    enabled=True,
                    lead_seconds=300,
                )
                run = await database.runs.create_planned(
                    source.id,
                    scheduled_for_utc=datetime(2026, 1, 2, minute // 60, 0, tzinfo=UTC),
                    generation_due_at_utc=datetime(2026, 1, 2, minute // 60, 0, tzinfo=UTC)
                    - timedelta(minutes=5),
                )
                run_ids.append(run.id)
            return run_ids
        finally:
            await database.close()

    run_ids = asyncio.run(seed())
    text = asyncio.run(runs_text(initialized_settings, limit=2))

    assert "completed" not in text
    assert all(f"{run_id:>3}" not in f"\n{text}" for run_id in run_ids[:-2])
    assert f"{run_ids[-1]:>3}" in f"\n{text}"
    assert f"{run_ids[-2]:>3}" in f"\n{text}"


def test_runs_text_reports_outcome_reasons(
    initialized_settings: ControllerSettings,
) -> None:
    async def seed() -> None:
        database = Database(initialized_settings)
        try:
            source = await database.create_daily_announcement(
                minute_of_day=8 * 60,
                template="It is {time}.",
                enabled=True,
                lead_seconds=300,
            )
            run = await database.runs.create_planned(
                source.id,
                scheduled_for_utc=datetime(2026, 1, 2, 8, 0, tzinfo=UTC),
                generation_due_at_utc=datetime(2026, 1, 2, 7, 55, tzinfo=UTC),
            )
            await database.runs.transition(
                run.id,
                expected_status="planned",
                new_status="skipped",
                reason="announcements paused",
            )
        finally:
            await database.close()

    asyncio.run(seed())
    text = asyncio.run(runs_text(initialized_settings))

    assert "skipped" in text
    assert "announcements paused" in text
    assert "2026-01-02 08:00 UTC" in text


def test_runs_text_reports_an_empty_history(
    initialized_settings: ControllerSettings,
) -> None:
    assert "No announcement runs yet." in asyncio.run(runs_text(initialized_settings))
