import math

import numpy as np
import sounddevice as sd
import soundfile as sf
from scipy.signal import resample_poly

from config import CHIME_AUDIO, SOUND_OFF_AUDIO


def resample_audio(samples, from_rate, to_rate):
    if from_rate == to_rate:
        return samples

    gcd = math.gcd(from_rate, to_rate)
    return resample_poly(samples, to_rate // gcd, from_rate // gcd)


def load_mono_audio(path, target_sr):
    samples, sample_rate = sf.read(path)

    if samples.ndim > 1:
        samples = samples.mean(axis=1)

    return resample_audio(samples, sample_rate, target_sr)


def prepend_chime(speech, speech_sr):
    chime = load_mono_audio(CHIME_AUDIO, speech_sr)
    sound_off = load_mono_audio(SOUND_OFF_AUDIO, speech_sr)
    return np.concatenate([chime, speech, sound_off])


def prepare_for_playback(samples, sample_rate):
    output_rate = int(sd.query_devices(kind="output")["default_samplerate"])
    samples = resample_audio(samples, sample_rate, output_rate)
    return np.ascontiguousarray(samples, dtype=np.float32), output_rate


def play_audio(samples, sample_rate):
    samples, sample_rate = prepare_for_playback(samples, sample_rate)
    sd.play(samples, sample_rate)
    sd.wait()
