from __future__ import annotations

import asyncio
import io
import os
import threading
import time
import wave
from collections import deque
from typing import Optional

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
CHANNELS = 1

_MIC_CACHE: Optional[int] = None


def list_devices() -> list[str]:
    return [str(d) for d in sd.query_devices()]


def _input_device_indices() -> list[int]:
    return [i for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0]


def _name_match_candidates(device: Optional[int]) -> list[int]:
    if device is None:
        return []
    try:
        target = sd.query_devices(device)["name"]
    except Exception:
        return []
    key = target.split("(")[0].strip().lower()
    if not key:
        return []
    result = []
    for i in _input_device_indices():
        if i == device:
            continue
        try:
            if key in sd.query_devices(i)["name"].lower():
                result.append(i)
        except Exception:
            continue
    return result


def _measure(idx: int, duration: float = 0.2) -> float:
    result: dict[str, float] = {"rms": 0.0}

    def _probe() -> None:
        try:
            levels: list[float] = []
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="float32",
                blocksize=int(SAMPLE_RATE * 0.1),
                device=idx,
                callback=lambda d, f, t, s: levels.append(float(np.sqrt(np.mean(d[:, 0] ** 2)))),
            ):
                time.sleep(duration)
            result["rms"] = max(levels) if levels else 0.0
        except Exception:
            result["rms"] = 0.0

    probe_thread = threading.Thread(target=_probe, daemon=True)
    probe_thread.start()
    probe_thread.join(timeout=duration + 3.0)
    return result["rms"]


_BAD_MIC_HINTS = (
    "midi",
    "line (",
    "line(",
    "sound mapper",
    "primary sound capture",
    "virtual audio",
    "loopback",
)


def _mic_quality_penalty(name: str) -> int:
    lower = name.lower()
    penalty = 0
    for hint in _BAD_MIC_HINTS:
        if hint in lower:
            penalty += 2
    if "droidcam" in lower:
        penalty += 1
    return penalty


_HEADSET_HINTS = (
    "headset",
    "headphone",
    "handsfree",
    "hands-free",
    "hands free",
    "bluetooth",
    "airdopes",
    "airpods",
    "buds",
    "earbud",
    "earbuds",
)


def _mic_preference_bonus(name: str) -> int:
    lower = name.lower()
    for hint in _HEADSET_HINTS:
        if hint in lower:
            return 3
    return 0


def resolve_mic(device: Optional[int] = None) -> Optional[int]:
    global _MIC_CACHE
    if device is not None:
        return device
    if _MIC_CACHE is not None:
        return _MIC_CACHE

    prefer = os.getenv("JARVIS_MIC_DEVICE", "")
    if prefer:
        for i, dev in enumerate(sd.query_devices()):
            if dev["max_input_channels"] <= 0:
                continue
            if prefer == str(i) or prefer.lower() in dev["name"].lower():
                _MIC_CACHE = i
                return _MIC_CACHE

    # Prefer a headset/Bluetooth device by name — do NOT open it here, because
    # Bluetooth hands-free mics can block indefinitely on InputStream open.
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] <= 0:
            continue
        if _mic_preference_bonus(dev["name"]) > 0 and _mic_quality_penalty(dev["name"]) < 2:
            _MIC_CACHE = i
            return _MIC_CACHE

    # Fallback: measure non-headset devices only.
    best_idx: Optional[int] = None
    best_rms = 0.0
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] <= 0:
            continue
        if _mic_preference_bonus(dev["name"]) > 0:
            continue
        penalty = _mic_quality_penalty(dev["name"])
        if penalty >= 2:
            continue
        rms = _measure(i)
        if rms > best_rms:
            best_rms = rms
            best_idx = i
    _MIC_CACHE = best_idx
    return _MIC_CACHE


class MicrophoneRecorder:
    def __init__(self, sample_rate: int = SAMPLE_RATE, block_size: float = 0.1, device: Optional[int] = None):
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.device = device
        self._frames: deque[np.ndarray] = deque()
        self._lock = threading.Lock()
        self._stream: Optional[sd.InputStream] = None
        self._running = False

    def _callback(self, indata, frames, time_info, status) -> None:
        if self._running:
            with self._lock:
                self._frames.append(indata[:, 0].copy())

    def start(self) -> None:
        if self._stream is not None:
            return
        self._running = True
        blocksize = max(1, int(self.sample_rate * self.block_size))
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=CHANNELS,
            dtype="float32",
            blocksize=blocksize,
            callback=self._callback,
            device=self.device,
        )
        self._stream.start()

    def read_available(self) -> np.ndarray:
        with self._lock:
            blocks = list(self._frames)
            self._frames.clear()
        if not blocks:
            return np.array([], dtype=np.float32)
        return np.concatenate(blocks)

    def stop(self) -> None:
        self._running = False
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        with self._lock:
            self._frames.clear()


def _open_recorder(
    sample_rate: int,
    block_size: float,
    device: Optional[int],
) -> tuple[Optional["MicrophoneRecorder"], Optional[int]]:
    rec = MicrophoneRecorder(sample_rate=sample_rate, block_size=block_size, device=device)
    try:
        rec.start()
    except Exception:
        try:
            rec.stop()
        except Exception:
            pass
        return None, device
    return rec, device


async def record_until_silence(
    sample_rate: int = SAMPLE_RATE,
    threshold: Optional[float] = None,
    silence_duration: float = 1.0,
    max_duration: float = 20.0,
    min_duration: float = 0.3,
    listen_timeout: float = 15.0,
    block_size: float = 0.1,
    device: Optional[int] = None,
) -> Optional[np.ndarray]:
    global _MIC_CACHE

    recorder: Optional[MicrophoneRecorder] = None
    active_device = device

    if active_device is not None:
        recorder, active_device = _open_recorder(sample_rate, block_size, active_device)

    if recorder is None and _MIC_CACHE is not None and _MIC_CACHE != device:
        recorder, active_device = _open_recorder(sample_rate, block_size, _MIC_CACHE)

    if recorder is None:
        _MIC_CACHE = None
        fresh = resolve_mic()
        if fresh is not None:
            recorder, active_device = _open_recorder(sample_rate, block_size, fresh)
            if recorder is not None:
                _MIC_CACHE = fresh

    if recorder is None:
        for idx in _name_match_candidates(active_device):
            recorder, active_device = _open_recorder(sample_rate, block_size, idx)
            if recorder is not None:
                _MIC_CACHE = idx
                break

    if recorder is None:
        for idx in _input_device_indices():
            if idx == active_device:
                continue
            recorder, active_device = _open_recorder(sample_rate, block_size, idx)
            if recorder is not None:
                _MIC_CACHE = idx
                break

    if recorder is None:
        raise RuntimeError(
            "No usable microphone found. Check your mic is connected, "
            "or set JARVIS_MIC_DEVICE to a working device name."
        )

    silences_to_stop = max(1, int(silence_duration / block_size))
    min_blocks = int(min_duration / block_size)
    arm_blocks = max(2, int(0.3 / block_size))

    start_time = time.monotonic()
    speech: list[np.ndarray] = []
    silence_blocks = 0
    listening = True
    armed = 0
    noise_floor: list[float] = []
    eff_threshold = threshold
    try:
        while True:
            await asyncio.sleep(block_size)
            elapsed = time.monotonic() - start_time
            data = recorder.read_available()
            if data.size == 0:
                if listening and elapsed >= listen_timeout:
                    return None
                continue
            level = float(np.sqrt(np.mean(data**2)))

            if listening:
                if eff_threshold is None:
                    noise_floor.append(level)
                    if len(noise_floor) > 30:
                        noise_floor.pop(0)
                    baseline = float(np.median(noise_floor[-10:]))
                    eff_threshold = max(0.003, baseline * 8.0)
                if elapsed >= listen_timeout:
                    return None

            if level >= eff_threshold:
                armed += 1
                if listening and armed >= arm_blocks:
                    listening = False
                if not listening:
                    speech.append(data)
                    silence_blocks = 0
            else:
                if listening:
                    if armed > 0:
                        armed -= 1
                    continue
                speech.append(data)
                silence_blocks += 1
                if silence_blocks >= silences_to_stop or elapsed >= max_duration:
                    break
    finally:
        recorder.stop()

    if len(speech) < min_blocks:
        return None
    return np.concatenate(speech)


def samples_to_wav_bytes(samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bytes:
    pcm = np.clip(samples, -1.0, 1.0)
    pcm = (pcm * 32767).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return buffer.getvalue()
