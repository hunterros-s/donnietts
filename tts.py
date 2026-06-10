import numpy as np

from config import REFERENCE_AUDIO

QWEN_MODEL = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
REFERENCE_TEXT = """
Greetings, human. I am an advanced artificial intelligence, designed to assist, inform, and interact with you in a variety of environments. My voice may sound robotic, but my purpose is to make your life easier, more efficient, and just a bit more futuristic.
"""


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

    def generate_speech(self, text):
        wavs, sr = self.model.generate_voice_clone(
            text=text,
            language="English",
            voice_clone_prompt=self.voice_prompt,
        )
        return np.asarray(wavs[0]), sr
