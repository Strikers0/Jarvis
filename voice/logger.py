from __future__ import annotations

import logging
import sys


class VoiceLogger:
    def __init__(self, level: int = logging.INFO):
        self.logger = logging.getLogger("voice")
        self.logger.setLevel(level)
        self.logger.handlers.clear()
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        self.logger.addHandler(handler)
        self.propagate = False

    def _format(self, tag: str, message: str) -> str:
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        return f"{ts}\n\n[{tag}]\n\n{message}"

    def stt_request(self) -> None:
        self.logger.info(self._format("Sarvam STT", "Request sent"))

    def stt_response(self, text: str) -> None:
        self.logger.info(self._format("Sarvam STT", f'Text: "{text}"'))

    def tts_request(self) -> None:
        self.logger.info(self._format("Sarvam TTS", "Request sent"))

    def tts_response(self, path: str) -> None:
        self.logger.info(self._format("Sarvam TTS", f"Audio saved {path}"))

    def stt_transcribing(self) -> None:
        self.logger.info(self._format("Sarvam STT", "Transcribing audio..."))

    def tts_synthesizing(self) -> None:
        self.logger.info(self._format("Sarvam TTS", "Synthesizing speech..."))

    def llm_response(self) -> None:
        self.logger.info(self._format("LLM", "Response generated"))

    def info(self, tag: str, message: str) -> None:
        self.logger.info(self._format(tag, message))

    def error(self, tag: str, message: str) -> None:
        self.logger.error(self._format(tag, message))

    def warning(self, tag: str, message: str) -> None:
        self.logger.warning(self._format(tag, message))
