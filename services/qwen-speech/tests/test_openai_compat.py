import io
import wave

import httpx
import pytest
from openai import AsyncOpenAI

from qwen_speech.app import create_app
from qwen_speech.backend import FakeSpeechBackend


@pytest.mark.asyncio
async def test_official_openai_client_can_generate_wav() -> None:
    app = create_app(backend=FakeSpeechBackend(), api_key="test-token")
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        client = AsyncOpenAI(
            base_url="http://test/v1",
            api_key="test-token",
            http_client=http_client,
        )
        response = await client.audio.speech.create(
            model="fake-tts",
            input="Hello from the OpenAI client.",
            voice="announcer",
            response_format="wav",
        )
        audio = response.content

    with wave.open(io.BytesIO(audio), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == 24_000
        assert wav.getnframes() > 0


@pytest.mark.asyncio
async def test_api_key_is_required_when_configured() -> None:
    app = create_app(backend=FakeSpeechBackend(), api_key="test-token")
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

    assert response.status_code == 401
    assert response.json()["error"]["type"] == "authentication_error"


@pytest.mark.asyncio
async def test_health_and_model_discovery() -> None:
    app = create_app(backend=FakeSpeechBackend(), api_key="test-token")
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        live = await client.get("/health/live")
        ready = await client.get("/health/ready")
        models = await client.get("/v1/models", headers={"Authorization": "Bearer test-token"})

    assert live.json() == {"status": "ok"}
    assert ready.json() == {"status": "ready"}
    assert models.json()["data"][0]["id"] == "fake-tts"
