from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from core.llm import LLMMessage, LLMProvider
from core.conversation import ConversationManager
from core.personality import PersonalityManager
from voice.sarvam_stt import SarvamSTT
from voice.sarvam_tts import SarvamTTS
from voice.logger import VoiceLogger


class PipelineError(Exception):
    pass


class STTError(PipelineError):
    pass


class TTSError(PipelineError):
    pass


class AudioPipeline:
    def __init__(
        self,
        llm: LLMProvider,
        stt: SarvamSTT,
        tts: SarvamTTS,
        conversation: ConversationManager,
        personality_manager: PersonalityManager,
        logger: Optional[VoiceLogger] = None,
    ):
        self.llm = llm
        self.stt = stt
        self.tts = tts
        self.conversation = conversation
        self.personality_manager = personality_manager
        self.logger = logger or VoiceLogger()
        self._running = False

    def _get_system_prompt(self) -> str:
        p = self.personality_manager.get_active()
        return p.system_prompt if p else "You are JARVIS, a helpful AI assistant."

    async def process(self, audio_data: bytes) -> str:
        self.logger.stt_transcribing()
        try:
            transcript = await self.stt.transcribe(audio_data)
        except Exception as e:
            self.logger.error("Sarvam STT", str(e))
            raise STTError(f"Sarvam STT failed: {e}")
        if not transcript:
            return ""
        self.logger.stt_response(transcript)

        user_message = LLMMessage(role="user", content=transcript)
        self.conversation.add_message(user_message)

        self.logger.llm_response()
        try:
            response = await self.llm.chat(
                self.conversation.get_history(),
                system_prompt=self._get_system_prompt(),
            )
        except asyncio.TimeoutError:
            raise PipelineError("LLM timeout")
        self.conversation.add_message(LLMMessage(role="assistant", content=response.content))

        return response.content

    async def process_to_speech(
        self, audio_data: bytes, output_path: str | Path = "runtime/response.wav"
    ) -> str:
        text = await self.process(audio_data)
        if not text:
            return ""
        self.logger.tts_synthesizing()
        try:
            await self.tts.synthesize(text, output_path=output_path)
        except Exception as e:
            self.logger.error("Sarvam TTS", str(e))
            self.logger.info("Sarvam TTS", f"Fallback: {text}")
            return text
        self.logger.tts_response(str(output_path))
        return text

    async def process_file(self, wav_path: str | Path) -> str:
        audio_data = Path(wav_path).read_bytes()
        return await self.process(audio_data)

    async def reset(self) -> None:
        self.logger.info("Pipeline", "Reset pipeline")
