import io
from typing import Protocol

import numpy as np
import soundfile as sf

from config import (
    REFERENCE_AUDIO,
    TTS_API_KEY,
    TTS_BASE_URL,
    TTS_INSTRUCTIONS,
    TTS_MODEL,
    TTS_PROVIDER,
    TTS_TIMEOUT_SECONDS,
    TTS_VOICE,
)

QWEN_MODEL = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
REFERENCE_TEXT = """
Greetings, human. I am an advanced artificial intelligence, designed to assist, inform, and interact with you in a variety of environments. My voice may sound robotic, but my purpose is to make your life easier, more efficient, and just a bit more futuristic.
"""


class TTSProvider(Protocol):
    def generate_speech(self, text: str) -> tuple[np.ndarray, int]: ...


class QwenTTSProvider:
    def __init__(self):
        import torch
        from qwen_tts import Qwen3TTSModel

        self.model = Qwen3TTSModel.from_pretrained(
            QWEN_MODEL,
            device_map="cpu",
            dtype=torch.float32,
            attn_implementation="sdpa",
        )
        self.voice_prompt = self.model.create_voice_clone_prompt(
            ref_audio=str(REFERENCE_AUDIO),
            ref_text=REFERENCE_TEXT,
            x_vector_only_mode=False,
        )

    def generate_speech(self, text: str) -> tuple[np.ndarray, int]:
        wavs, sample_rate = self.model.generate_voice_clone(
            text=text,
            language="English",
            voice_clone_prompt=self.voice_prompt,
        )
        return np.asarray(wavs[0]), sample_rate


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


def create_tts_provider(provider: str = TTS_PROVIDER) -> TTSProvider:
    if provider == "embedded":
        return QwenTTSProvider()
    if provider == "openai":
        return OpenAICompatibleTTSProvider()
    raise RuntimeError(f"Unknown TTS_PROVIDER: {provider}")
