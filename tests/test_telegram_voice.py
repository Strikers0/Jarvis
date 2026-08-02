from __future__ import annotations

import wave
from pathlib import Path

import pytest

from core.services.telegram_voice import TelegramVoiceProcessor


def _write_wav(path: Path) -> bytes:
    import io
    import struct

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(struct.pack("<h", 0) * 1600)
    data = buffer.getvalue()
    path.write_bytes(data)
    return data


class FakeSTT:
    async def transcribe(self, audio_data: bytes, language: str = ""):
        return "turn on the lights"


class FakeTTS:
    async def synthesize(self, text: str, output_path="runtime/response.wav", voice=""):
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"WAV")
        return p


class FakeSession:
    def __init__(self):
        self.chat_calls = []

    async def chat(self, text: str, user_id: str = "default"):
        self.chat_calls.append((text, user_id))
        return "I turned on the lights."

    def get_voice_for_active(self):
        return "tanya"


def test_audio_decode_roundtrip(tmp_path):
    from voice.audio import decode_audio_to_wav_bytes

    wav = tmp_path / "sample.wav"
    raw = _write_wav(wav)
    decoded = decode_audio_to_wav_bytes(wav)
    assert decoded[:4] == b"RIFF"
    assert decoded == raw or len(decoded) >= 3200


def test_write_wav_bytes(tmp_path):
    from voice.audio import write_wav_bytes

    out = write_wav_bytes(b"RIFFxx", tmp_path / "sub" / "a.wav")
    assert out.exists()
    assert out.read_bytes() == b"RIFFxx"


@pytest.mark.asyncio
async def test_processor_unavailable_without_stt():
    proc = TelegramVoiceProcessor(FakeSession(), stt=None, tts=None)
    assert not proc.available


@pytest.mark.asyncio
async def test_processor_flows(tmp_path):
    proc = TelegramVoiceProcessor(
        FakeSession(),
        stt=FakeSTT(),
        tts=FakeTTS(),
        output_dir=tmp_path / "runtime",
    )
    assert proc.available

    class FakeDownload:
        def __init__(self, wav: Path):
            self.wav = wav

        def __call__(self, file):
            Path(file).write_bytes(self.wav.read_bytes())
            return None

    class FakeMessage:
        def __init__(self, wav: Path):
            self._wav = wav

        def download_media(self, file=None):
            return FakeDownload(self._wav)(file)

    wav = tmp_path / "in.wav"
    _write_wav(wav)
    reply, voice_path = await proc.process_event(FakeMessage(wav), user_id="777")
    assert reply == "I turned on the lights."
    assert voice_path is not None
    assert voice_path.exists()


@pytest.mark.asyncio
async def test_processor_download_failure(tmp_path):
    proc = TelegramVoiceProcessor(
        FakeSession(),
        stt=FakeSTT(),
        tts=FakeTTS(),
        output_dir=tmp_path / "runtime",
    )

    class BadDownload:
        def __call__(self, file):
            raise RuntimeError("network down")

    class FakeMessage:
        def download_media(self, file=None):
            return BadDownload()(file)

    reply, voice_path = await proc.process_event(FakeMessage(), user_id="777")
    assert "couldn't download" in reply
    assert voice_path is None
