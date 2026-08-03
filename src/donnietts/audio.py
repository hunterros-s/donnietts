"""Audio loading, chime preparation, and playback."""

import math
import os
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf
from scipy.signal import resample_poly


DEFAULT_CHIME_AUDIO = "assets/startup3.mp3"
DEFAULT_SOUND_OFF_AUDIO = "assets/sound_off.mp3"

CHIME_AUDIO = Path(os.getenv("DONNIETTS_CHIME_AUDIO", DEFAULT_CHIME_AUDIO))
SOUND_OFF_AUDIO = Path(os.getenv("DONNIETTS_SOUND_OFF_AUDIO", DEFAULT_SOUND_OFF_AUDIO))


def resample_audio(samples: np.ndarray, from_rate: int, to_rate: int) -> np.ndarray:
    if from_rate == to_rate:
        return samples

    gcd = math.gcd(from_rate, to_rate)
    return resample_poly(samples, to_rate // gcd, from_rate // gcd)


def load_mono_audio(path: str | Path, target_sr: int) -> np.ndarray:
    samples, sample_rate = sf.read(path)

    if samples.ndim > 1:
        samples = samples.mean(axis=1)

    return resample_audio(samples, sample_rate, target_sr)


def prepend_chime(speech: np.ndarray, speech_sr: int) -> np.ndarray:
    chime = load_mono_audio(CHIME_AUDIO, speech_sr)
    sound_off = load_mono_audio(SOUND_OFF_AUDIO, speech_sr)
    return np.concatenate([chime, speech, sound_off])


def prepare_for_playback(samples: np.ndarray, sample_rate: int) -> tuple[np.ndarray, int]:
    output_rate = int(sd.query_devices(kind="output")["default_samplerate"])
    samples = resample_audio(samples, sample_rate, output_rate)
    return np.ascontiguousarray(samples, dtype=np.float32), output_rate


def play_audio(samples: np.ndarray, sample_rate: int) -> None:
    samples, sample_rate = prepare_for_playback(samples, sample_rate)
    sd.play(samples, sample_rate)
    sd.wait()


def play_wav_file(path: str | Path) -> None:
    """Load a generated WAV, prepend the chime, and play it synchronously."""
    samples, sample_rate = sf.read(path, dtype="float32")
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    combined = prepend_chime(samples, sample_rate)
    play_audio(combined, sample_rate)
