import asyncio
import io
import sys
import types
import wave

import numpy as np
import pytest

from qwen_speech.qwen_backend import QwenSpeechBackend
from qwen_speech.schemas import CreateSpeechRequest


class FakeQwenModel:
    def __init__(self):
        self.prompt_audio_exists = False

    def create_voice_clone_prompt(self, *, ref_audio, ref_text, x_vector_only_mode):
        from pathlib import Path

        self.prompt_audio_exists = Path(ref_audio).is_file()
        assert ref_text
        assert x_vector_only_mode is False
        return {"voice": "fake-prompt"}

    def generate_voice_clone(self, *, text, language, voice_clone_prompt):
        assert text == "Hello from Qwen."
        assert language == "English"
        assert voice_clone_prompt == {"voice": "fake-prompt"}
        return [np.zeros(2_400, dtype=np.float32)], 24_000


class FakeQwenModelFactory:
    model = FakeQwenModel()

    @classmethod
    def from_pretrained(cls, model_path, **kwargs):
        assert model_path == "test/model"
        assert kwargs["device_map"] == "cpu"
        assert kwargs["attn_implementation"] == "sdpa"
        return cls.model


@pytest.mark.asyncio
async def test_qwen_backend_loads_voice_and_generates_wav(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(float32="float32"))
    monkeypatch.setitem(
        sys.modules,
        "qwen_tts",
        types.SimpleNamespace(Qwen3TTSModel=FakeQwenModelFactory),
    )

    backend = QwenSpeechBackend(model_path="test/model", model_id="test-qwen")
    await backend.start()
    try:
        for _ in range(100):
            if backend.ready or backend.status == "failed":
                break
            await asyncio.sleep(0.01)

        assert backend.ready, backend.load_error
        assert FakeQwenModelFactory.model.prompt_audio_exists

        audio = await backend.synthesize(
            CreateSpeechRequest(
                model="test-qwen",
                input="Hello from Qwen.",
                voice="announcer",
                response_format="wav",
            )
        )
    finally:
        await backend.stop()

    with wave.open(io.BytesIO(audio.content), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getframerate() == 24_000
        assert wav.getnframes() == 2_400
