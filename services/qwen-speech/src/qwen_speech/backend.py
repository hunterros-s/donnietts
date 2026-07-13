import io
import math
import struct
import wave
from dataclasses import dataclass
from typing import Protocol

from qwen_speech.schemas import CreateSpeechRequest, ModelObject


@dataclass(frozen=True)
class SynthesizedAudio:
    content: bytes
    media_type: str


class SpeechBackendError(Exception):
    def __init__(self, message: str, *, param: str | None = None, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.param = param
        self.code = code


class SpeechBackend(Protocol):
    @property
    def ready(self) -> bool: ...

    def models(self) -> list[ModelObject]: ...

    async def synthesize(self, request: CreateSpeechRequest) -> SynthesizedAudio: ...


class FakeSpeechBackend:
    """Deterministic backend used to establish and test the HTTP contract."""

    model_id = "fake-tts"
    sample_rate = 24_000

    @property
    def ready(self) -> bool:
        return True

    def models(self) -> list[ModelObject]:
        return [ModelObject(id=self.model_id)]

    async def synthesize(self, request: CreateSpeechRequest) -> SynthesizedAudio:
        if request.model != self.model_id:
            raise SpeechBackendError(
                f"Unknown model: {request.model}",
                param="model",
                code="model_not_found",
            )
        if request.response_format != "wav":
            raise SpeechBackendError(
                "The scaffold backend currently supports response_format='wav' only",
                param="response_format",
                code="unsupported_response_format",
            )
        if request.stream_format != "audio":
            raise SpeechBackendError(
                "The scaffold backend does not support SSE streaming",
                param="stream_format",
                code="unsupported_stream_format",
            )

        return SynthesizedAudio(
            content=self._generate_wav(request.input, request.voice_id),
            media_type="audio/wav",
        )

    def _generate_wav(self, text: str, voice: str) -> bytes:
        duration_seconds = 0.2
        frame_count = round(self.sample_rate * duration_seconds)
        seed = sum(text.encode()) + sum(voice.encode())
        frequency = 320 + seed % 160
        amplitude = 0.15 * 32767

        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self.sample_rate)
            frames = bytearray()
            for index in range(frame_count):
                sample = round(amplitude * math.sin(2 * math.pi * frequency * index / self.sample_rate))
                frames.extend(struct.pack("<h", sample))
            wav.writeframes(frames)
        return output.getvalue()
