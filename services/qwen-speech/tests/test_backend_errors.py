import httpx
import pytest

from qwen_speech.app import create_app
from qwen_speech.backend import FakeSpeechBackend, SpeechBackendNotReady


class NotReadyBackend(FakeSpeechBackend):
    @property
    def ready(self) -> bool:
        return False

    async def synthesize(self, request):
        raise SpeechBackendNotReady("The speech model is not ready", code="model_not_ready")


@pytest.mark.asyncio
async def test_backend_not_ready_maps_to_service_unavailable() -> None:
    app = create_app(backend=NotReadyBackend())
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/audio/speech",
            json={
                "model": "fake-tts",
                "input": "Hello.",
                "voice": "announcer",
                "response_format": "wav",
            },
        )

    assert response.status_code == 503
    assert response.json()["error"] == {
        "message": "The speech model is not ready",
        "type": "server_error",
        "param": None,
        "code": "model_not_ready",
    }
