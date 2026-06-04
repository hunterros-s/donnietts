import numpy as np

from config import REFERENCE_AUDIO

QWEN_MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
REFERENCE_TEXT = "Attention. The time is ten fifteen A M. Current conditions are overcast. The temperature is sixty eight degrees."


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
