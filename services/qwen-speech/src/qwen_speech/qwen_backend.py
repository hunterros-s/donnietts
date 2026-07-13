import asyncio
import io
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from importlib import resources
from typing import Any

from qwen_speech.backend import (
    SpeechBackendBusy,
    SpeechBackendError,
    SpeechBackendFailure,
    SpeechBackendNotReady,
    SynthesizedAudio,
)
from qwen_speech.schemas import CreateSpeechRequest, ModelObject
from qwen_speech.voice_registry import VoiceDefinition, VoiceRegistry


DEFAULT_MODEL_PATH = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
DEFAULT_MODEL_ID = "qwen3-tts-0.6b"

logger = logging.getLogger(__name__)


class QwenSpeechBackend:
    """Serializes all model initialization and inference on one worker thread."""

    def __init__(
        self,
        *,
        model_path: str = DEFAULT_MODEL_PATH,
        model_id: str = DEFAULT_MODEL_ID,
        max_pending_requests: int = 2,
    ):
        if max_pending_requests < 1:
            raise ValueError("max_pending_requests must be at least 1")

        self.model_path = model_path
        self.model_id = model_id
        self.max_pending_requests = max_pending_requests

        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="qwen-tts")
        self._state_lock = threading.Lock()
        self._state = "not_started"
        self._load_error: str | None = None
        self._pending_requests = 0

        self._model: Any | None = None
        self._voices: VoiceRegistry | None = None
        self._voice_prompts: dict[str, Any] = {}
        self._load_future: asyncio.Future[None] | None = None

    @classmethod
    def from_environment(cls) -> "QwenSpeechBackend":
        return cls(
            model_path=os.getenv("QWEN_SPEECH_MODEL_PATH", DEFAULT_MODEL_PATH),
            model_id=os.getenv("QWEN_SPEECH_MODEL_ID", DEFAULT_MODEL_ID),
            max_pending_requests=int(os.getenv("QWEN_SPEECH_MAX_PENDING_REQUESTS", "2")),
        )

    @property
    def ready(self) -> bool:
        with self._state_lock:
            return self._state == "ready"

    @property
    def status(self) -> str:
        with self._state_lock:
            return self._state

    @property
    def load_error(self) -> str | None:
        with self._state_lock:
            return self._load_error

    def models(self) -> list[ModelObject]:
        return [ModelObject(id=self.model_id, owned_by="qwen")]

    async def start(self) -> None:
        with self._state_lock:
            if self._state != "not_started":
                return
            self._state = "loading"

        loop = asyncio.get_running_loop()
        self._load_future = loop.run_in_executor(self._executor, self._load)

    async def stop(self) -> None:
        with self._state_lock:
            if self._state == "stopped":
                return
            self._state = "stopping"

        await asyncio.to_thread(self._executor.shutdown, wait=True, cancel_futures=True)
        with self._state_lock:
            self._state = "stopped"

    async def synthesize(self, request: CreateSpeechRequest) -> SynthesizedAudio:
        self._validate_request(request)

        if not self.ready:
            raise SpeechBackendNotReady(
                "The speech model is not ready",
                code="model_not_ready",
            )

        with self._state_lock:
            if self._pending_requests >= self.max_pending_requests:
                raise SpeechBackendBusy(
                    "The speech generation queue is full",
                    code="queue_full",
                )
            self._pending_requests += 1

        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(self._executor, self._generate, request)
        except SpeechBackendError:
            raise
        except Exception as error:
            logger.exception("Qwen speech generation failed")
            raise SpeechBackendFailure(
                "Speech generation failed",
                code="generation_failed",
            ) from error
        finally:
            with self._state_lock:
                self._pending_requests -= 1

    def _load(self) -> None:
        try:
            import torch
            from qwen_tts import Qwen3TTSModel

            model = Qwen3TTSModel.from_pretrained(
                self.model_path,
                device_map="cpu",
                dtype=torch.float32,
                attn_implementation="sdpa",
            )
            voices = VoiceRegistry.from_package()
            prompts = {
                voice.id: self._create_voice_prompt(model, voice)
                for voice in voices.values()
            }
        except Exception as error:
            logger.exception("Failed to load Qwen speech backend")
            with self._state_lock:
                self._load_error = f"{type(error).__name__}: {error}"
                self._state = "failed"
            return

        self._model = model
        self._voices = voices
        self._voice_prompts = prompts
        with self._state_lock:
            self._state = "ready"
        logger.info("Qwen speech backend ready with %d voice(s)", len(prompts))

    @staticmethod
    def _create_voice_prompt(model: Any, voice: VoiceDefinition) -> Any:
        with resources.as_file(voice.reference_audio) as audio_path:
            return model.create_voice_clone_prompt(
                ref_audio=str(audio_path),
                ref_text=voice.reference_text,
                x_vector_only_mode=False,
            )

    def _generate(self, request: CreateSpeechRequest) -> SynthesizedAudio:
        import numpy as np
        import soundfile as sf

        assert self._model is not None
        assert self._voices is not None

        voice = self._voices.get(request.voice_id)
        if voice is None:
            raise SpeechBackendError(
                f"Unknown voice: {request.voice_id}",
                param="voice",
                code="voice_not_found",
            )

        wavs, sample_rate = self._model.generate_voice_clone(
            text=request.input,
            language=voice.language,
            voice_clone_prompt=self._voice_prompts[voice.id],
        )
        samples = np.asarray(wavs[0], dtype=np.float32)

        output = io.BytesIO()
        sf.write(output, samples, sample_rate, format="WAV", subtype="PCM_16")
        return SynthesizedAudio(content=output.getvalue(), media_type="audio/wav")

    def _validate_request(self, request: CreateSpeechRequest) -> None:
        if request.model != self.model_id:
            raise SpeechBackendError(
                f"Unknown model: {request.model}",
                param="model",
                code="model_not_found",
            )
        if request.response_format != "wav":
            raise SpeechBackendError(
                "The Qwen backend currently supports response_format='wav' only",
                param="response_format",
                code="unsupported_response_format",
            )
        if request.stream_format != "audio":
            raise SpeechBackendError(
                "The Qwen backend does not support SSE streaming",
                param="stream_format",
                code="unsupported_stream_format",
            )
        if request.instructions:
            raise SpeechBackendError(
                "The Qwen voice-cloning model does not support instructions",
                param="instructions",
                code="unsupported_instructions",
            )
        if request.speed != 1.0:
            raise SpeechBackendError(
                "The Qwen voice-cloning model does not support speed adjustment",
                param="speed",
                code="unsupported_speed",
            )
