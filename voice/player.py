from __future__ import annotations

import threading
import winsound
from pathlib import Path
from typing import Optional

_PLAY_THREAD: Optional[threading.Thread] = None


def play_wav_start(path: str | Path, mic_device: Optional[int] = None) -> bool:
    """Play a WAV file through Windows' native audio stack (clear quality).

    sounddevice/PortAudio's MME backend resamples poorly and sounds blurry
    on some systems; winsound uses the same clean audio path as everything
    else on Windows. Playback runs in a daemon thread so the async loop is
    not blocked.
    """
    global _PLAY_THREAD
    stop_playback()
    path = Path(path)
    if not path.exists():
        return False

    def _play() -> None:
        try:
            winsound.PlaySound(str(path), winsound.SND_FILENAME)
        except Exception:
            pass

    _PLAY_THREAD = threading.Thread(target=_play, daemon=True)
    _PLAY_THREAD.start()
    return True


def is_playing() -> bool:
    global _PLAY_THREAD
    return bool(_PLAY_THREAD is not None and _PLAY_THREAD.is_alive())


def stop_playback() -> None:
    global _PLAY_THREAD
    try:
        winsound.PlaySound(None, winsound.SND_PURGE)
    except Exception:
        pass
    _PLAY_THREAD = None
