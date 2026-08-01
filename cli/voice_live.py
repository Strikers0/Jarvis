from __future__ import annotations

import asyncio
import os
from pathlib import Path

from rich.console import Console

from core.config import ConfigManager
from core.conversation import MemoryAwareConversationManager
from core.llm import LLMFactory
from core.memory import MemoryManager
from core.personality import PersonalityManager
from core.tools import (
    BrowserAutomationToolSet,
    DesktopAutomationToolSet,
    MediaToolSet,
    PermissionManager,
    SystemToolSet,
    ToolDispatcher,
    ToolRegistry,
)
from core.tools.personality import PersonalityToolSet
from voice.controller import run_voice
from voice.microphone import resolve_mic
from voice.sarvam_stt import SarvamSTT
from voice.sarvam_tts import SarvamTTS

console = Console()


def build_tool_dispatcher(config, conversation, memory_manager, personality_manager):
    registry = ToolRegistry()
    for tool_set in (
        DesktopAutomationToolSet(),
        BrowserAutomationToolSet(),
        MediaToolSet(),
        SystemToolSet(),
        PersonalityToolSet(personality_manager),
    ):
        registry.register_set(tool_set)

    permission_manager = PermissionManager()
    permissions = {
        tool_name: perm_cfg.level
        for tool_name, perm_cfg in config.tool.permissions.items()
    }
    permission_manager.load_config(permissions)

    dispatcher = ToolDispatcher(
        registry=registry,
        permission_manager=permission_manager,
        confirm_callback=lambda tool_name, args: True,
    )

    console.print(f"[dim]Loaded {len(registry)} tools[/dim]")
    return dispatcher


def build_system_prompt_builder(config, conversation, personality_manager):
    def builder() -> str:
        personality = personality_manager.get_active()
        base = personality.system_prompt if personality else "You are JARVIS, a helpful AI assistant."
        base += (
            "\n\nThis is a voice conversation. Reply in Hinglish (Hindi written in Latin/Roman "
            "script mixed with English), since you are being read aloud by a Hindi voice. "
            "Keep replies short, conversational, and easy to speak naturally. "
            "Write numbers and simple words in English, use Hindi for the rest (e.g. "
            "'tumhara message send ho gaya')."
        )
        if config.tool.enabled:
            base += (
                "\n\nYou have access to tools that can perform actions on the user's system "
                "(open apps, search the web, play music, etc.). "
                "Use tools ONLY when the user explicitly asks you to perform an action. "
                "For general conversation, questions, or after successfully completing a task, "
                "respond naturally without calling any tools."
            )
        return conversation.build_system_prompt_with_memory(base)

    return builder


def build_sarvam(config) -> tuple[SarvamSTT, SarvamTTS]:
    sarvam_cfg = config.sarvam
    api_key = sarvam_cfg.api_key or os.getenv("SARVAM_API_KEY", "")
    if not api_key:
        raise RuntimeError("SARVAM_API_KEY is not set. Set it in .env to use voice mode.")
    stt = SarvamSTT(
        api_key=api_key,
        model=sarvam_cfg.stt_model,
        language_code=sarvam_cfg.stt_language_code,
        with_translation=sarvam_cfg.stt_with_translation,
    )
    tts = SarvamTTS(
        api_key=api_key,
        model=sarvam_cfg.tts_model,
        language_code=sarvam_cfg.tts_language_code,
        voice=sarvam_cfg.tts_speaker,
        speed=sarvam_cfg.tts_pace,
    )
    return stt, tts


async def voice_live(config_path: str | Path | None = None) -> None:
    config_manager = ConfigManager(config_path)
    config = config_manager.config

    personality_manager = PersonalityManager()
    active_name = config.personality.active
    if not personality_manager.set_active(active_name):
        personality_manager.set_active("jarvis")

    memory_manager = MemoryManager(db_path=config.memory.db_path)
    conversation = MemoryAwareConversationManager(
        db_path=Path.cwd() / "conversations.db",
        max_history=config.conversation.max_history,
        memory_manager=memory_manager,
        auto_extract=config.memory.auto_extract,
        max_facts_in_context=config.memory.max_facts_in_context,
    )
    conversation.create_session("JARVIS Voice Session")

    llm = LLMFactory.create(config)

    dispatcher = None
    system_prompt_builder = None
    if config.tool.enabled:
        dispatcher = build_tool_dispatcher(config, conversation, memory_manager, personality_manager)
        system_prompt_builder = build_system_prompt_builder(config, conversation, personality_manager)
    stt, tts = build_sarvam(config)

    mic_device = resolve_mic()
    if mic_device is None:
        console.print("[red]No working microphone found. Set JARVIS_MIC_DEVICE to a device name or index.[/red]")
        mic_device = None
    else:
        import sounddevice as sd
        mic_name = sd.query_devices(mic_device)["name"]
        console.print(f"[dim]Using microphone: {mic_name}[/dim]")

    try:
        await run_voice(
            config=config,
            llm=llm,
            stt=stt,
            tts=tts,
            conversation=conversation,
            personality_manager=personality_manager,
            dispatcher=dispatcher,
            system_prompt_builder=system_prompt_builder,
            mic_device=mic_device,
        )
    finally:
        memory_manager.close()
        if llm:
            try:
                await llm.close()
            except Exception:
                pass


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(voice_live())
