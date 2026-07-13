import asyncio
import sqlite3

import pytest
from fastapi.testclient import TestClient

from donnietts.app import create_app
from donnietts.database import (
    AnnouncementRevisionConflictError,
    AnnouncementSnapshot,
    Database,
)
from donnietts.settings import ControllerSettings


API = "/api/v1/announcements"
FUTURE_TIME = "2100-01-01T14:30:00-05:00"
LATER_FUTURE_TIME = "2100-01-02T14:30:00-05:00"


def test_migration_seeds_the_legacy_schedule(client: TestClient) -> None:
    response = client.get(API)

    assert response.status_code == 200
    announcements = response.json()
    assert len(announcements) == 14
    assert [item["time"] for item in announcements] == [
        f"{hour:02d}:00" for hour in range(8, 22)
    ]
    assert all(item["kind"] == "daily" for item in announcements)
    assert all(item["enabled"] for item in announcements)
    assert all(item["lead_seconds"] == 300 for item in announcements)
    assert all(item["revision"] == 1 for item in announcements)

    settings = client.get("/api/v1/settings")
    assert settings.status_code == 200
    assert settings.json()["timezone"] == "America/Detroit"
    assert client.get("/health/ready").status_code == 200


def test_daily_announcement_lifecycle(client: TestClient) -> None:
    created = client.post(
        f"{API}/daily",
        json={
            "time": "07:30",
            "template": "  Good morning {weekday}.  ",
            "lead_seconds": 120,
        },
    )

    assert created.status_code == 201
    announcement = created.json()
    announcement_id = announcement["id"]
    assert announcement["kind"] == "daily"
    assert announcement["enabled"] is True
    assert announcement["time"] == "07:30"
    assert announcement["run_at_utc"] is None
    assert announcement["template"] == "Good morning {weekday}."
    assert announcement["lead_seconds"] == 120
    assert announcement["revision"] == 1
    assert client.get(f"{API}/{announcement_id}").json() == announcement

    updated = client.patch(
        f"{API}/{announcement_id}",
        json={
            "expected_revision": 1,
            "time": "07:45",
            "template": "Updated at {time}.",
            "enabled": False,
            "lead_seconds": 60,
        },
    )

    assert updated.status_code == 200
    assert updated.json()["revision"] == 2
    assert updated.json()["time"] == "07:45"
    assert updated.json()["template"] == "Updated at {time}."
    assert updated.json()["enabled"] is False
    assert updated.json()["lead_seconds"] == 60

    stale_update = client.patch(
        f"{API}/{announcement_id}",
        json={"expected_revision": 1, "enabled": True},
    )
    assert stale_update.status_code == 409

    stale_delete = client.delete(f"{API}/{announcement_id}?expected_revision=1")
    assert stale_delete.status_code == 409
    assert client.delete(f"{API}/{announcement_id}?expected_revision=2").status_code == 204
    assert client.get(f"{API}/{announcement_id}").status_code == 404


def test_daily_times_are_unique_on_create_and_update(client: TestClient) -> None:
    first = client.post(f"{API}/daily", json={"time": "07:30", "template": "First"})
    second = client.post(f"{API}/daily", json={"time": "07:31", "template": "Second"})
    assert first.status_code == 201
    assert second.status_code == 201

    duplicate_create = client.post(
        f"{API}/daily",
        json={"time": "07:30", "template": "Duplicate"},
    )
    assert duplicate_create.status_code == 409

    second_id = second.json()["id"]
    duplicate_update = client.patch(
        f"{API}/{second_id}",
        json={"expected_revision": 1, "time": "07:30"},
    )
    assert duplicate_update.status_code == 409
    unchanged = client.get(f"{API}/{second_id}").json()
    assert unchanged["time"] == "07:31"
    assert unchanged["revision"] == 1


@pytest.mark.parametrize(
    "value",
    ["7:30", "07:3", "24:00", "23:60", "07.30", "００:００", ""],
)
def test_daily_time_requires_strict_ascii_hhmm(client: TestClient, value: str) -> None:
    response = client.post(
        f"{API}/daily",
        json={"time": value, "template": "Invalid time"},
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "template",
    [
        "",
        "   ",
        "Hello {person}.",
        "Hello {time",
        "Hello {}.",
        "Hello {time!r}.",
        "Hello {time:>20}.",
        "Hello {time.__class__}.",
    ],
)
def test_invalid_templates_are_rejected(client: TestClient, template: str) -> None:
    response = client.post(
        f"{API}/daily",
        json={"time": "07:30", "template": template},
    )

    assert response.status_code == 422


def test_all_supported_template_fields_are_accepted(client: TestClient) -> None:
    fields = [
        "time",
        "weekday",
        "date",
        "location",
        "city",
        "state",
        "latitude",
        "longitude",
        "weather_condition",
        "current_temp",
        "high_temp",
        "low_temp",
        "wind",
        "wind_speed",
        "precip_chance",
    ]
    template = " ".join(f"{{{field}}}" for field in fields)

    response = client.post(
        f"{API}/daily",
        json={"time": "07:30", "template": template},
    )

    assert response.status_code == 201
    assert response.json()["template"] == template


def test_one_off_lifecycle_normalizes_timestamps_to_utc(client: TestClient) -> None:
    created = client.post(
        f"{API}/one-off",
        json={"run_at": FUTURE_TIME, "template": "Appointment at {time}."},
    )

    assert created.status_code == 201
    announcement = created.json()
    assert announcement["kind"] == "one_off"
    assert announcement["time"] is None
    assert announcement["run_at_utc"] == "2100-01-01T19:30:00Z"
    assert announcement["revision"] == 1

    updated = client.patch(
        f"{API}/{announcement['id']}",
        json={
            "expected_revision": 1,
            "run_at": LATER_FUTURE_TIME,
            "lead_seconds": 60,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["run_at_utc"] == "2100-01-02T19:30:00Z"
    assert updated.json()["lead_seconds"] == 60
    assert updated.json()["revision"] == 2


def test_multiple_one_offs_may_share_a_timestamp(client: TestClient) -> None:
    payload = {"run_at": FUTURE_TIME, "template": "One-off"}

    assert client.post(f"{API}/one-off", json=payload).status_code == 201
    assert client.post(f"{API}/one-off", json=payload).status_code == 201


@pytest.mark.parametrize(
    "run_at",
    ["2100-01-01T14:30:00", "2000-01-01T14:30:00Z", 4102486200],
)
def test_one_off_requires_a_future_rfc3339_timestamp_with_offset(
    client: TestClient,
    run_at: str | int,
) -> None:
    response = client.post(
        f"{API}/one-off",
        json={"run_at": run_at, "template": "Invalid timestamp"},
    )

    assert response.status_code == 422


def test_schedule_fields_cannot_cross_announcement_kinds(client: TestClient) -> None:
    daily = client.post(f"{API}/daily", json={"time": "07:30", "template": "Daily"}).json()
    one_off = client.post(
        f"{API}/one-off",
        json={"run_at": FUTURE_TIME, "template": "One-off"},
    ).json()

    daily_response = client.patch(
        f"{API}/{daily['id']}",
        json={"expected_revision": 1, "run_at": LATER_FUTURE_TIME},
    )
    one_off_response = client.patch(
        f"{API}/{one_off['id']}",
        json={"expected_revision": 1, "time": "07:45"},
    )

    assert daily_response.status_code == 422
    assert one_off_response.status_code == 422


@pytest.mark.parametrize(
    "patch",
    [
        {"expected_revision": 1},
        {"expected_revision": 1, "enabled": None},
        {"expected_revision": 1, "time": None},
        {"expected_revision": 1, "run_at": None},
        {"expected_revision": 1, "template": None},
        {"expected_revision": 1, "lead_seconds": None},
        {"expected_revision": 1, "lead_seconds": -1},
        {"expected_revision": 0, "enabled": False},
        {"expected_revision": 1, "unknown": True},
    ],
)
def test_invalid_patches_are_rejected(client: TestClient, patch: dict) -> None:
    response = client.patch(f"{API}/1", json=patch)

    assert response.status_code == 422


def test_concurrent_updates_allow_only_one_writer(migrated_settings: ControllerSettings) -> None:
    async def exercise() -> tuple[list[AnnouncementSnapshot], list[Exception], int]:
        database = Database(migrated_settings)
        try:
            created = await database.create_daily_announcement(
                minute_of_day=7 * 60 + 15,
                template="Race test",
                enabled=True,
                lead_seconds=300,
            )
            results = await asyncio.gather(
                database.update_announcement(
                    created.id,
                    expected_revision=1,
                    template="First writer",
                ),
                database.update_announcement(
                    created.id,
                    expected_revision=1,
                    template="Second writer",
                ),
                return_exceptions=True,
            )
            successes = [item for item in results if isinstance(item, AnnouncementSnapshot)]
            errors = [item for item in results if isinstance(item, Exception)]
            current = await database.get_announcement(created.id)
            return successes, errors, current.revision
        finally:
            await database.close()

    successes, errors, revision = asyncio.run(exercise())

    assert len(successes) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], AnnouncementRevisionConflictError)
    assert revision == 2


def test_readiness_rejects_a_pending_migration(migrated_settings: ControllerSettings) -> None:
    with sqlite3.connect(migrated_settings.database_path) as connection:
        connection.execute("UPDATE alembic_version SET version_num = '0003'")

    with TestClient(create_app(migrated_settings)) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
