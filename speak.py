import sys

import numpy as np

from audio import play_audio, prepend_chime
from config import DEFAULT_TEMPLATE, REFERENCE_AUDIO
from template import render_template

QWEN_MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
REFERENCE_TEXT = "Attention. The time is ten fifteen A M. Current conditions are overcast. The temperature is sixty eight degrees."


def generate_speech(text):
    import torch
    from qwen_tts import Qwen3TTSModel

    model = Qwen3TTSModel.from_pretrained(
        QWEN_MODEL,
        device_map="cpu",
        dtype=torch.float32,
        attn_implementation="sdpa",
    )

    voice_prompt = model.create_voice_clone_prompt(
        ref_audio=str(REFERENCE_AUDIO),
        ref_text=REFERENCE_TEXT,
        x_vector_only_mode=False,
    )

    wavs, sr = model.generate_voice_clone(
        text=text,
        language="English",
        voice_clone_prompt=voice_prompt,
    )

    return np.asarray(wavs[0]), sr


def main():
    template = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else DEFAULT_TEMPLATE
    announcement = render_template(template)
    print(announcement)

    speech, sr = generate_speech(announcement)
    combined = prepend_chime(speech, sr)

    try:
        play_audio(combined, sr)
    except Exception as exc:
        raise SystemExit(f"Playback failed: {exc}") from exc


if __name__ == "__main__":
    main()
