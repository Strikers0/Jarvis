from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Optional

from rich.console import Console

from core.conversation import ConversationManager
from core.llm import LLMMessage, LLMProvider
from core.personality import PersonalityManager
from voice import player
from voice.logger import VoiceLogger
from voice.microphone import record_until_silence, samples_to_wav_bytes
from voice.sarvam_stt import SarvamSTT
from voice.sarvam_tts import SarvamTTS

console = Console()


class VoiceController:
    def __init__(
        self,
        llm: LLMProvider,
        stt: SarvamSTT,
        tts: SarvamTTS,
        conversation: ConversationManager,
        personality_manager: PersonalityManager,
        dispatcher: Optional[Any] = None,
        system_prompt_builder: Any = None,
        mic_device: Optional[int] = None,
        silence_duration: float = 0.5,
        listen_timeout: float = 15.0,
        logger: Optional[VoiceLogger] = None,
    ):
        self.llm = llm
        self.stt = stt
        self.tts = tts
        self.conversation = conversation
        self.personality_manager = personality_manager
        self.dispatcher = dispatcher
        self.system_prompt_builder = system_prompt_builder
        self.mic_device = mic_device
        self.silence_duration = silence_duration
        self.listen_timeout = listen_timeout
        self.logger = logger or VoiceLogger()
        self._running = False
        self.response_path = Path("runtime/response.wav")

    def _get_system_prompt(self) -> str:
        if self.system_prompt_builder is not None:
            return self.system_prompt_builder()
        p = self.personality_manager.get_active()
        return p.system_prompt if p else "You are JARVIS, a helpful AI assistant."

    async def run(self) -> None:
        self._running = True
        console.print("[bold cyan]Voice mode active. Speak... (Ctrl+C to stop)[/bold cyan]")
        while self._running:
            try:
                await self._turn()
            except KeyboardInterrupt:
                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                console.print(f"[red]Error:[/red] {e}")
                await asyncio.sleep(2.0)

    async def _turn(self) -> None:
        console.print("[dim]Listening...[/dim]")
        samples = await record_until_silence(
            device=self.mic_device,
            silence_duration=self.silence_duration,
            listen_timeout=self.listen_timeout,
        )
        if samples is None or len(samples) == 0:
            console.print("[dim]No speech detected.[/dim]")
            return

        wav_bytes = samples_to_wav_bytes(samples)
        console.print("[cyan]Transcribing...[/cyan]")
        self.logger.stt_transcribing()
        try:
            transcript = await self.stt.transcribe(wav_bytes)
        except Exception as e:
            console.print(f"[red]STT failed:[/red] {e}")
            return
        self.logger.stt_response(transcript)
        if not transcript.strip():
            console.print("[dim]No speech detected.[/dim]")
            return
        console.print(f"[bold green]You:[/bold green] {transcript}")

        user_message = LLMMessage(role="user", content=transcript)
        self.conversation.add_message(user_message)
        system_prompt = self._get_system_prompt()

        console.print("[cyan]Thinking...[/cyan]")
        self.logger.llm_response()
        try:
            if self.dispatcher is not None:
                response = await self.dispatcher.chat_with_tools(
                    llm=self.llm,
                    messages=self.conversation.get_history(),
                    system_prompt=system_prompt,
                    max_tool_rounds=5,
                )
            else:
                response = await self.llm.chat(
                    self.conversation.get_history(),
                    system_prompt=system_prompt,
                )
        except Exception as e:
            console.print(f"[red]LLM failed:[/red] {e}")
            return

        self.conversation.add_message(LLMMessage(role="assistant", content=response.content))
        reply = response.content or "(no response)"
        console.print(f"[bold cyan]{self._assistant_name()}:[/bold cyan] {reply}")

        console.print("[cyan]Speaking...[/cyan]")
        self.logger.tts_synthesizing()
        try:
            out = await self.tts.synthesize(reply, output_path=self.response_path)
            self.logger.tts_response(str(out))
            player.play_wav_start(out, mic_device=self.mic_device)
            while player.is_playing():
                await asyncio.sleep(0.1)
        except Exception as e:
            console.print(f"[yellow]TTS/playback skipped:[/yellow] {e}")

    def _assistant_name(self) -> str:
        p = self.personality_manager.get_active()
        return (p.name if p else "jarvis").replace("_", " ").title()

    def stop(self) -> None:
        self._running = False

    async def cleanup(self) -> None:
        player.stop_playback()
        try:
            await self.stt.close()
        except Exception:
            pass
        try:
            await self.tts.close()
        except Exception:
            pass
        try:
            await self.llm.close()
        except Exception:
            pass
        self.conversation.close()


async def run_voice(
    config: Any,
    llm: LLMProvider,
    stt: SarvamSTT,
    tts: SarvamTTS,
    conversation: ConversationManager,
    personality_manager: PersonalityManager,
    dispatcher: Optional[Any] = None,
    system_prompt_builder: Any = None,
    mic_device: Optional[int] = None,
) -> None:
    controller = VoiceController(
        llm=llm,
        stt=stt,
        tts=tts,
        conversation=conversation,
        personality_manager=personality_manager,
        dispatcher=dispatcher,
        system_prompt_builder=system_prompt_builder,
        mic_device=mic_device,
        silence_duration=getattr(config.voice, "silence_duration", 0.5),
        listen_timeout=getattr(config.voice, "listen_timeout", 15.0),
    )
    try:
        await controller.run()
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopping voice mode.[/yellow]")
    finally:
        await controller.cleanup()
