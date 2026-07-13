import asyncio
import json

import httpx
import pytest

from donnietts.settings import SpeechSettings
from donnietts.speech_client import OpenAICompatibleSpeechClient


def speech_settings(**overrides) -> SpeechSettings:
    values = {
        "base_url": "http://speech.test/v1",
        "api_key": "secret",
        "model": "test-model",
        "voice": "announcer",
        "instructions": "Speak clearly.",
        "generation_timeout_seconds": 30,
        "health_url": None,
        "status_timeout_seconds": 1,
    }
    values.update(overrides)
    return SpeechSettings(**values)


def test_speech_generation_uses_async_openai_compatible_request() -> None:
    async def exercise() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert request.url == httpx.URL("http://speech.test/v1/audio/speech")
            assert request.headers["Authorization"] == "Bearer secret"
            assert json.loads(request.content) == {
                "model": "test-model",
                "input": "Hello Donnie.",
                "voice": "announcer",
                "response_format": "wav",
                "instructions": "Speak clearly.",
            }
            return httpx.Response(200, content=b"RIFF-test-wave")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OpenAICompatibleSpeechClient(http_client, speech_settings())
            assert await client.generate_wav("Hello Donnie.") == b"RIFF-test-wave"

    asyncio.run(exercise())


def test_speech_generation_propagates_http_errors() -> None:
    async def exercise() -> None:
        async def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"error": {"message": "warming"}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = OpenAICompatibleSpeechClient(
                http_client,
                speech_settings(api_key="", instructions=None),
            )
            with pytest.raises(httpx.HTTPStatusError):
                await client.generate_wav("Hello Donnie.")

    asyncio.run(exercise())
