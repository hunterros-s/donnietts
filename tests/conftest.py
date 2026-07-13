from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from donnietts.app import create_app
from donnietts.migration_runner import upgrade_database
from donnietts.settings import ControllerSettings, SpeechSettings


@pytest.fixture
def controller_settings(tmp_path) -> ControllerSettings:
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
    )


@pytest.fixture
def migrated_settings(controller_settings: ControllerSettings) -> ControllerSettings:
    upgrade_database(controller_settings)
    return controller_settings


@pytest.fixture
def client(migrated_settings: ControllerSettings) -> Iterator[TestClient]:
    with TestClient(create_app(migrated_settings)) as test_client:
        yield test_client
