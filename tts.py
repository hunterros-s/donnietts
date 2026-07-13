import asyncio
import io
from typing import Protocol

import httpx
import numpy as np
import soundfile as sf

from config import SPEECH_SETTINGS
from donnietts.settings import SpeechSettings
from donnietts.speech_client import OpenAICompatibleSpeechClient


class TTSProvider(Protocol):
    async def generate_speech(self, text: str) -> tuple[np.ndarray, int]: ...


class OpenAICompatibleTTSProvider:
    def __init__(
        self,
        client: httpx.AsyncClient,
        settings: SpeechSettings = SPEECH_SETTINGS,
    ):
        self.speech_client = OpenAICompatibleSpeechClient(client, settings)

    async def generate_speech(self, text: str) -> tuple[np.ndarray, int]:
        wav = await self.speech_client.generate_wav(text)
        return await asyncio.to_thread(self._decode_wav, wav)

    @staticmethod
    def _decode_wav(wav: bytes) -> tuple[np.ndarray, int]:
        samples, sample_rate = sf.read(io.BytesIO(wav), dtype="float32")
        if samples.ndim > 1:
            samples = samples.mean(axis=1)
        return np.asarray(samples, dtype=np.float32), sample_rate


def create_tts_provider(client: httpx.AsyncClient) -> TTSProvider:
    return OpenAICompatibleTTSProvider(client)
