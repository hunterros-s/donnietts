import asyncio
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from donnietts.app import create_app
from donnietts.database import Database
from donnietts.schedule import EMPTY_SCHEDULE
from donnietts.settings import ControllerSettings, SpeechSettings


@pytest.fixture
def controller_settings(tmp_path) -> ControllerSettings:
    schedule_path = tmp_path / "schedule.yaml"
    schedule_path.write_text(EMPTY_SCHEDULE, encoding="utf-8")
    return ControllerSettings(
        speech=SpeechSettings(
            base_url="http://speech.invalid/v1",
            api_key="test",
            model="test-model",
            voice="test-voice",
            instructions=None,
            generation_timeout_seconds=1,
            health_url=None,
            status_timeout_seconds=0.1,
        ),
        database_path=tmp_path / "controller.sqlite3",
        schedule_path=schedule_path,
    )


@pytest.fixture
def initialized_settings(controller_settings: ControllerSettings) -> ControllerSettings:
    database = Database(controller_settings)
    try:
        asyncio.run(database.initialize())
    finally:
        asyncio.run(database.close())
    return controller_settings


@pytest.fixture
def client(initialized_settings: ControllerSettings) -> Iterator[TestClient]:
    with TestClient(create_app(initialized_settings)) as test_client:
        yield test_client
