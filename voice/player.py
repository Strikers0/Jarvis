from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import sounddevice as sd


def play_wav_start(path: str | Path) -> bool:
    with wave.open(str(path), "rb") as wf:
        frames = wf.readframes(wf.getnframes())
        rate = wf.getframerate()
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
    dtype = {1: np.int8, 2: np.int16, 4: np.int32}.get(sampwidth, np.int16)
    audio = np.frombuffer(frames, dtype=dtype)
    if channels > 1:
        audio = audio.reshape(-1, channels)
    sd.play(audio, rate)
    return True


def is_playing() -> bool:
    try:
        stream = sd.get_stream()
        return bool(stream and stream.active)
    except Exception:
        return False


def stop_playback() -> None:
    try:
        sd.stop()
    except Exception:
        pass
