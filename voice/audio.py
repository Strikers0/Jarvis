from __future__ import annotations

import io
import wave
from pathlib import Path
from typing import Union


def decode_audio_to_wav_bytes(path: Union[str, Path]) -> bytes:
    """Decode any audio file to 16kHz mono s16 WAV bytes.

    Uses PyAV, so formats like OGG/Opus (Telegram voice notes) are supported.
    """
    import av

    with av.open(str(path)) as container:
        container.streams.audio[0]
        resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
        frames = []
        for frame in container.decode(audio=0):
            frame.pts = None
            for f in resampler.resample(frame):
                frames.append(f.to_ndarray().tobytes())

    audio_data = b"".join(frames)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(audio_data)
    return buffer.getvalue()


def write_wav_bytes(wav_bytes: bytes, output_path: Union[str, Path]) -> Path:
    """Persist raw WAV bytes to disk, creating parent directories."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(wav_bytes)
    return out
