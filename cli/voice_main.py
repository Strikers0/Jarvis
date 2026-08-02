from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from rich.console import Console

from core.config import ConfigManager
from core.conversation import MemoryAwareConversationManager
from core.llm import LLMFactory, LLMMessage
from core.memory import MemoryManager
from core.personality import PersonalityManager
from voice.audio import decode_audio_to_wav_bytes
from voice.logger import VoiceLogger
from voice.sarvam_stt import SarvamSTT
from voice.sarvam_tts import SarvamTTS

console = Console()


class AudioFileProcessor:
    def __init__(self):
        self.config_manager = ConfigManager()
        self.config = self.config_manager.config
        self.personality_manager = PersonalityManager()
        self.memory_manager = MemoryManager(db_path=self.config.memory.db_path)
        self.conversation = MemoryAwareConversationManager(
            db_path=Path.cwd() / "conversations.db",
            max_history=self.config.conversation.max_history,
            memory_manager=self.memory_manager,
            auto_extract=self.config.memory.auto_extract,
            max_facts_in_context=self.config.memory.max_facts_in_context,
        )
        self.llm = None
        self.sarvam_stt: Optional[SarvamSTT] = None
        self.sarvam_tts: Optional[SarvamTTS] = None
        self.logger = VoiceLogger()
        self._init_personality()
        self._init_llm()
        self._init_session()
        self._init_sarvam()

    def _init_sarvam(self) -> None:
        sarvam_cfg = self.config.sarvam
        api_key = sarvam_cfg.api_key if sarvam_cfg.api_key else ""
        if not api_key:
            import os
            api_key = os.getenv("SARVAM_API_KEY", "")
        self.sarvam_stt = SarvamSTT(
            api_key=api_key,
            model=sarvam_cfg.stt_model,
            language_code=sarvam_cfg.stt_language_code,
            with_translation=sarvam_cfg.stt_with_translation,
        )
        self.sarvam_tts = SarvamTTS(
            api_key=api_key,
            model=sarvam_cfg.tts_model,
            language_code=sarvam_cfg.tts_language_code,
            voice=self.personality_manager.get_sarvam_voice(),
            speed=sarvam_cfg.tts_pace,
        )

    def _init_personality(self) -> None:
        active_name = self.config.personality.active
        personality = self.personality_manager.set_active(active_name)
        if not personality:
            self.personality_manager.set_active("jarvis")

    def _init_llm(self) -> None:
        try:
            self.llm = LLMFactory.create(self.config)
        except ValueError as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            import sys
            sys.exit(1)

    def _init_session(self) -> None:
        self.conversation.create_session("JARVIS Session")

    def _get_active_personality(self) -> str:
        p = self.personality_manager.get_active()
        return p.name if p else "jarvis"

    def _get_system_prompt(self) -> str:
        p = self.personality_manager.get_active()
        return p.system_prompt if p else "You are JARVIS, a helpful AI assistant."

    async def process(self, file_path: str) -> None:
        path = Path(file_path)
        if not path.exists():
            console.print(f"[red]File not found:[/red] {file_path}")
            return

        console.print(f"\n[cyan]Loading {path.name}...[/cyan]")

        try:
            wav_bytes = decode_audio_to_wav_bytes(path)
        except Exception as e:
            console.print(f"[red]Failed to decode audio:[/red] {e}")
            return

        console.print("[cyan]Converting audio...[/cyan]")

        console.print("[cyan]Running STT...[/cyan]")
        try:
            self.logger.stt_transcribing()
            transcript = await self.sarvam_stt.transcribe(wav_bytes)
        except Exception as e:
            console.print(f"[red]STT failed:[/red] {e}")
            return
        self.logger.stt_response(transcript)
        console.print("\n[bold green]Transcript:[/bold green]")
        console.print(f'  "{transcript}"\n')

        if not transcript.strip():
            console.print("[yellow]No speech detected.[/yellow]")
            return

        console.print("[cyan]Generating response...[/cyan]")
        user_message = LLMMessage(role="user", content=transcript)
        self.conversation.add_message(user_message)
        system_prompt = self.conversation.build_system_prompt_with_memory(self._get_system_prompt())
        try:
            self.logger.llm_response()
            response = await self.llm.chat(
                self.conversation.get_history(),
                system_prompt=system_prompt,
            )
        except Exception as e:
            console.print(f"[red]LLM failed:[/red] {e}")
            return
        self.conversation.add_message(LLMMessage(role="assistant", content=response.content))
        assistant_name = self._get_active_personality().replace("_", " ").title()
        console.print(f"[bold cyan]{assistant_name}:[/bold cyan] {response.content}\n")

        console.print("[cyan]Generating speech...[/cyan]")
        try:
            self.logger.tts_synthesizing()
            out = await self.sarvam_tts.synthesize(response.content)
            self.logger.tts_response(str(out))
            console.print(f"\n[bold green]Saved:[/bold green] {out}")
        except Exception as e:
            console.print(f"[red]TTS failed:[/red] {e}")

    async def cleanup(self) -> None:
        if self.sarvam_stt:
            try:
                await self.sarvam_stt.close()
            except Exception:
                pass
        if self.sarvam_tts:
            try:
                await self.sarvam_tts.close()
            except Exception:
                pass
        if self.llm:
            try:
                await self.llm.close()
            except Exception:
                pass
        self.conversation.close()
        self.memory_manager.close()


async def process_audio_file(file_path: str) -> None:
    from dotenv import load_dotenv
    load_dotenv()

    processor = AudioFileProcessor()
    try:
        await processor.process(file_path)
    finally:
        await processor.cleanup()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        asyncio.run(process_audio_file(sys.argv[1]))
    else:
        console.print("[red]Usage: python -m cli.voice_main <audio_file>[/red]")
