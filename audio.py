import math

import numpy as np
import sounddevice as sd
import soundfile as sf
from scipy.signal import resample_poly

from config import CHIME_AUDIO


def resample_audio(samples, from_rate, to_rate):
    if from_rate == to_rate:
        return samples

    gcd = math.gcd(from_rate, to_rate)
    return resample_poly(samples, to_rate // gcd, from_rate // gcd)


def prepend_chime(speech, speech_sr):
    chime, chime_sr = sf.read(CHIME_AUDIO)

    if chime.ndim > 1:
        chime = chime.mean(axis=1)

    chime = resample_audio(chime, chime_sr, speech_sr)
    return np.concatenate([chime, speech])


def prepare_for_playback(samples, sample_rate):
    output_rate = int(sd.query_devices(kind="output")["default_samplerate"])
    samples = resample_audio(samples, sample_rate, output_rate)
    return np.ascontiguousarray(samples, dtype=np.float32), output_rate


def play_audio(samples, sample_rate):
    samples, sample_rate = prepare_for_playback(samples, sample_rate)
    sd.play(samples, sample_rate)
    sd.wait()
