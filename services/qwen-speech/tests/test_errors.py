import httpx
import pytest

from qwen_speech.app import create_app
from qwen_speech.backend import FakeSpeechBackend


@pytest.mark.asyncio
async def test_validation_errors_use_openai_error_shape() -> None:
    app = create_app(backend=FakeSpeechBackend())
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/audio/speech",
            json={"model": "fake-tts", "input": "", "voice": "announcer", "response_format": "wav"},
        )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"
    assert response.json()["error"]["param"] == "input"


@pytest.mark.asyncio
async def test_unsupported_format_uses_openai_error_shape() -> None:
    app = create_app(backend=FakeSpeechBackend())
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/audio/speech",
            json={"model": "fake-tts", "input": "Hello.", "voice": "announcer"},
        )

    assert response.status_code == 400
    assert response.json()["error"] == {
        "message": "The scaffold backend currently supports response_format='wav' only",
        "type": "invalid_request_error",
        "param": "response_format",
        "code": "unsupported_response_format",
    }
