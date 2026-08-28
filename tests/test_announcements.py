import asyncio
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from donnietts.app import create_app
from donnietts.database import Database
from donnietts.schedule import ScheduleError, parse_schedule
from donnietts.settings import ControllerSettings


SCHEDULE_API = "/api/v1/schedule"


def schedule_text(*announcements: str, timezone: str = "UTC") -> str:
    items = "\n".join(announcements)
    return f"""version: 1
timezone: {timezone}
defaults:
  lead_seconds: 300
announcements:
{items if items else '  []'}
"""


def put_schedule(client: TestClient, text: str, etag: str | None = None):
    if etag is None:
        etag = client.get(SCHEDULE_API).headers["etag"]
    return client.put(
        SCHEDULE_API,
        content=text,
        headers={"Content-Type": "application/yaml", "If-Match": etag},
    )


def test_runs_endpoint_reports_durable_runs(
    client: TestClient,
    initialized_settings: ControllerSettings,
) -> None:
    async def seed() -> None:
        database = Database(initialized_settings)
        try:
            source = await database.create_daily_announcement(
                minute_of_day=7 * 60,
                template="It is {time}.",
                enabled=True,
                lead_seconds=300,
            )
            await database.runs.create_planned(
                source.id,
                scheduled_for_utc=datetime.fromisoformat("2100-01-02T15:00:00+00:00"),
                generation_due_at_utc=datetime.fromisoformat("2100-01-02T14:55:00+00:00"),
            )
        finally:
            await database.close()

    asyncio.run(seed())
    runs = client.get("/api/v1/runs").json()
    assert len(runs) == 1
    assert runs[0]["status"] == "planned"
    assert runs[0]["template_snapshot"] == "It is {time}."


def test_schedule_endpoint_returns_exact_yaml_and_path(
    client: TestClient,
    controller_settings: ControllerSettings,
) -> None:
    expected = controller_settings.resolved_schedule_path.read_text()
    response = client.get(SCHEDULE_API)

    assert response.status_code == 200
    assert response.text == expected
    assert response.headers["content-type"].startswith("application/yaml")
    assert response.headers["etag"].startswith('"')
    assert response.headers["x-schedule-path"] == str(controller_settings.resolved_schedule_path)


def test_put_schedule_preserves_text_and_projects_announcements(client: TestClient) -> None:
    text = schedule_text(
        """  - time: "07:30"
    template: >-
      Good morning {weekday}.
    lead_seconds: 120""",
        """  - run_at: "2100-01-01T14:30:00-05:00"
    template: Appointment at {time}.
    enabled: false""",
        timezone="America/Detroit",
    ) + "# keep this comment\n"

    response = put_schedule(client, text)
    assert response.status_code == 200
    assert response.text == text
    assert client.get(SCHEDULE_API).text == text

    announcements = client.get("/api/v1/announcements").json()
    assert len(announcements) == 2
    daily = next(item for item in announcements if item["kind"] == "daily")
    one_off = next(item for item in announcements if item["kind"] == "one_off")
    assert daily["time"] == "07:30"
    assert daily["template"] == "Good morning {weekday}."
    assert daily["lead_seconds"] == 120
    assert one_off["run_at_utc"] == "2100-01-01T19:30:00Z"
    assert one_off["enabled"] is False
    assert client.get("/api/v1/settings").json()["timezone"] == "America/Detroit"


def test_existing_lead_minutes_format_is_supported(client: TestClient) -> None:
    text = """defaults:
  lead_minutes: 5
announcements:
  - time: "08:00"
    template: Morning.
  - time: "09:00"
    lead_minutes: 2
    template: Update.
"""
    assert put_schedule(client, text).status_code == 200
    announcements = client.get("/api/v1/announcements").json()
    assert [item["lead_seconds"] for item in announcements] == [300, 120]


def test_schedule_save_uses_etag_to_prevent_overwrite(
    client: TestClient,
    controller_settings: ControllerSettings,
) -> None:
    stale_etag = client.get(SCHEDULE_API).headers["etag"]
    controller_settings.resolved_schedule_path.write_text(
        schedule_text("  - time: \"08:00\"\n    template: External edit."),
        encoding="utf-8",
    )

    response = put_schedule(client, schedule_text(), stale_etag)
    assert response.status_code == 409
    assert "reload" in response.json()["detail"]
    assert "External edit" in client.get(SCHEDULE_API).text


@pytest.mark.parametrize(
    ("fragment", "message"),
    [
        ('time: "7:30"\n    template: Invalid.', "HH:MM"),
        ('time: "24:00"\n    template: Invalid.', "HH:MM"),
        ('time: "08:00"\n    run_at: "2100-01-01T00:00:00Z"\n    template: Invalid.', "exactly one"),
        ('run_at: "2100-01-01T00:00:00"\n    template: Invalid.', "UTC offset"),
        ('time: "08:00"\n    template: Hello {person}.', "unknown template field"),
        ('time: "08:00"\n    template: ""', "must not be empty"),
        ('time: "08:00"\n    template: Invalid.\n    unknown: true', "Extra inputs"),
    ],
)
def test_invalid_schedules_are_rejected_without_changing_the_file(
    client: TestClient,
    fragment: str,
    message: str,
) -> None:
    before = client.get(SCHEDULE_API)
    invalid = f"announcements:\n  - {fragment}\n"
    response = put_schedule(client, invalid, before.headers["etag"])

    assert response.status_code == 422
    assert message.lower() in response.json()["detail"].lower()
    assert client.get(SCHEDULE_API).text == before.text


def test_yaml_syntax_error_reports_line_and_column(client: TestClient) -> None:
    response = put_schedule(client, "announcements:\n  - time: [\n")
    assert response.status_code == 422
    assert "line" in response.json()["detail"]
    assert "column" in response.json()["detail"]


def test_duplicate_daily_and_one_off_times_are_rejected() -> None:
    with pytest.raises(ScheduleError, match="duplicated"):
        parse_schedule(
            schedule_text(
                '  - time: "08:00"\n    template: First.',
                '  - time: "08:00"\n    template: Second.',
            )
        )
    with pytest.raises(ScheduleError, match="duplicated"):
        parse_schedule(
            schedule_text(
                '  - run_at: "2100-01-01T00:00:00Z"\n    template: First.',
                '  - run_at: "2100-01-01T00:00:00+00:00"\n    template: Second.',
            )
        )


def test_schedule_reconciliation_updates_and_removes_rows(client: TestClient) -> None:
    first = schedule_text(
        '  - time: "08:00"\n    template: First.',
        '  - time: "09:00"\n    template: Remove me.',
    )
    assert put_schedule(client, first).status_code == 200
    original = client.get("/api/v1/announcements").json()
    eight_id = next(item["id"] for item in original if item["time"] == "08:00")

    second = schedule_text('  - time: "08:00"\n    template: Updated.')
    assert put_schedule(client, second).status_code == 200
    current = client.get("/api/v1/announcements").json()
    assert len(current) == 1
    assert current[0]["id"] == eight_id
    assert current[0]["revision"] == 2
    assert current[0]["template"] == "Updated."


def test_invalid_external_edit_degrades_status_but_keeps_last_projection(
    client: TestClient,
    controller_settings: ControllerSettings,
) -> None:
    assert put_schedule(
        client,
        schedule_text('  - time: "08:00"\n    template: Valid.'),
    ).status_code == 200
    controller_settings.resolved_schedule_path.write_text("announcements: [", encoding="utf-8")

    status = client.get("/api/v1/status").json()
    assert status["status"] == "degraded"
    assert status["schedule"]["status"] == "invalid"
    assert len(client.get("/api/v1/announcements").json()) == 1
    assert client.get("/health/ready").status_code == 503


def test_announcement_mutation_routes_are_disabled(client: TestClient) -> None:
    assert client.post("/api/v1/announcements/daily", json={}).status_code == 405
    assert client.patch("/api/v1/announcements/1", json={}).status_code == 405
    assert client.delete("/api/v1/announcements/1").status_code == 405


def test_pause_setting_remains_operational_state(client: TestClient) -> None:
    assert client.patch(
        "/api/v1/settings", json={"announcements_enabled": False}
    ).json()["mode"] == "paused"
    assert client.patch(
        "/api/v1/settings", json={"timezone": "UTC"}
    ).status_code == 422


def test_app_initializes_a_fresh_database(controller_settings: ControllerSettings) -> None:
    with TestClient(create_app(controller_settings)) as client:
        assert client.get("/health/ready").status_code == 200
        assert client.get("/api/v1/settings").json()["announcements_enabled"] is True
        assert client.get("/api/v1/announcements").json() == []
