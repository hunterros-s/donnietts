import io
from typing import Protocol

import numpy as np
import soundfile as sf

from config import (
    TTS_API_KEY,
    TTS_BASE_URL,
    TTS_INSTRUCTIONS,
    TTS_MODEL,
    TTS_TIMEOUT_SECONDS,
    TTS_VOICE,
)


class TTSProvider(Protocol):
    def generate_speech(self, text: str) -> tuple[np.ndarray, int]: ...


class OpenAICompatibleTTSProvider:
    def __init__(
        self,
        *,
        base_url: str = TTS_BASE_URL,
        api_key: str = TTS_API_KEY,
        model: str = TTS_MODEL,
        voice: str = TTS_VOICE,
        instructions: str | None = TTS_INSTRUCTIONS,
        timeout_seconds: float = TTS_TIMEOUT_SECONDS,
    ):
        from openai import OpenAI

        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout_seconds,
        )
        self.model = model
        self.voice = voice
        self.instructions = instructions

    def generate_speech(self, text: str) -> tuple[np.ndarray, int]:
        request = {
            "model": self.model,
            "input": text,
            "voice": self.voice,
            "response_format": "wav",
        }
        if self.instructions:
            request["instructions"] = self.instructions

        response = self.client.audio.speech.create(**request)
        samples, sample_rate = sf.read(io.BytesIO(response.content), dtype="float32")
        if samples.ndim > 1:
            samples = samples.mean(axis=1)
        return np.asarray(samples, dtype=np.float32), sample_rate


def create_tts_provider() -> TTSProvider:
    return OpenAICompatibleTTSProvider()
