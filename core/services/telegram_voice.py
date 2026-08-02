from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any, Optional, Tuple

from core.session import JarvisSession
from voice.audio import decode_audio_to_wav_bytes
from voice.sarvam_stt import SarvamSTT
from voice.sarvam_tts import SarvamTTS

logger = logging.getLogger(__name__)


class TelegramVoiceProcessor:
    """Handles Telegram voice notes: download -> decode -> STT -> chat -> TTS."""

    def __init__(
        self,
        session: JarvisSession,
        stt: Optional[SarvamSTT] = None,
        tts: Optional[SarvamTTS] = None,
        output_dir: str | Path = "runtime",
    ):
        self.session = session
        self.stt = stt
        self.tts = tts
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @property
    def available(self) -> bool:
        return self.stt is not None and self.tts is not None

    async def process_event(
        self, event: Any, user_id: str = "default"
    ) -> Tuple[str, Optional[Path]]:
        """Download, transcribe, respond, and synthesize. Returns (reply_text, voice_path).

        `voice_path` is None when speech synthesis is unavailable.
        """
        message = getattr(event, "message", event)
        download = getattr(message, "download_media", None)
        if download is None:
            return "Sorry, I couldn't read that voice note.", None

        tmp_path: Optional[Path] = None
        try:
            fd, tmp_name = tempfile.mkstemp(suffix=".ogg")
            import os

            os.close(fd)
            tmp_path = Path(tmp_name)
            result = download(file=str(tmp_path))
            if hasattr(result, "__await__"):
                await result
        except Exception as e:
            logger.warning("Telegram voice download failed: %s", e)
            return "Sorry, I couldn't download that voice note.", None

        try:
            wav_bytes = decode_audio_to_wav_bytes(tmp_path)
        except Exception as e:
            logger.warning("Telegram voice decode failed: %s", e)
            return "Sorry, I couldn't decode that audio.", None
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

        transcript = await self._transcribe(wav_bytes)
        if not transcript:
            return "Sorry, I didn't catch any speech.", None

        reply = await self.session.chat(transcript, user_id=user_id)
        voice_path = await self._synthesize(reply)
        return reply, voice_path

    async def _transcribe(self, wav_bytes: bytes) -> str:
        if self.stt is None:
            return ""
        try:
            return await self.stt.transcribe(wav_bytes)
        except Exception as e:
            logger.warning("STT failed: %s", e)
            return ""

    async def _synthesize(self, text: str) -> Optional[Path]:
        if self.tts is None:
            return None
        try:
            voice = self.session.get_voice_for_active()
            out = self.output_dir / "telegram_response.wav"
            await self.tts.synthesize(text, output_path=out, voice=voice)
            return out
        except Exception as e:
            logger.warning("TTS failed: %s", e)
            return None
