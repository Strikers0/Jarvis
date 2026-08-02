from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Optional

from core.config import ConfigManager
from core.conversation import MemoryAwareConversationManager
from core.llm import LLMFactory, LLMMessage
from core.memory import MemoryManager
from core.personality import PersonalityManager
from core.services import ServiceManager
from core.tools import (
    BrowserAutomationToolSet,
    DesktopAutomationToolSet,
    MediaToolSet,
    PermissionManager,
    SystemToolSet,
    ToolDispatcher,
    ToolRegistry,
)

logger = logging.getLogger(__name__)

ConfirmCallback = Optional[Callable[[str, dict], bool]]
AsyncConfirmCallback = Optional[Callable[[str, dict], Any]]


class JarvisSession:
    """Shared runtime used by both the CLI and messaging platforms.

    Encapsulates LLM + personality + per-user conversation/memory + tools +
    services. `chat()` runs the same LLM-with-tools loop the CLI uses, scoped
    to a `user_id` so multi-user platforms get isolated sessions and memory.
    """

    def __init__(
        self,
        config_path: str | Path | None = None,
        config: Any = None,
        confirm_callback: ConfirmCallback = None,
        async_confirm_callback: AsyncConfirmCallback = None,
        create_conversation: bool = True,
    ):
        self.config_manager = None
        if config_path:
            self.config_manager = ConfigManager(config_path)
        elif config is None:
            self.config_manager = ConfigManager()
        if config is not None:
            self.config = config
        else:
            assert self.config_manager is not None
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
        self.llm: Optional[Any] = None
        self._llm_error: Optional[str] = None
        self.tool_registry = ToolRegistry()
        self.permission_manager = PermissionManager()
        self.tool_dispatcher: Optional[ToolDispatcher] = None
        self.service_manager: Optional[ServiceManager] = None
        self._user_sessions: dict[str, str] = {}
        self._init_personality()
        self._init_tools(confirm_callback, async_confirm_callback)
        if create_conversation:
            self._init_session()

    # ---- init ----

    def _init_personality(self) -> None:
        active_name = self.config.personality.active
        if not self.personality_manager.set_active(active_name):
            self.personality_manager.set_active("jarvis")

    def _ensure_llm(self) -> None:
        if self.llm is None and self._llm_error is None:
            try:
                self.llm = LLMFactory.create(self.config)
            except ValueError as e:
                self._llm_error = str(e)
        if self.llm is None:
            raise ValueError(self._llm_error or "LLM not initialized.")

    def _init_tools(
        self,
        confirm_callback: ConfirmCallback = None,
        async_confirm_callback: AsyncConfirmCallback = None,
    ) -> None:
        if not self.config.tool.enabled:
            return
        for ts in (
            DesktopAutomationToolSet(),
            BrowserAutomationToolSet(),
            MediaToolSet(),
            SystemToolSet(),
        ):
            self.tool_registry.register_set(ts)

        if self.config.services.enabled:
            self.service_manager = ServiceManager(self.config)
            self.tool_registry.register_set(self.service_manager)

        perms = {
            tool_name: perm_cfg.level
            for tool_name, perm_cfg in self.config.tool.permissions.items()
        }
        self.permission_manager.load_config(perms)

        self.tool_dispatcher = ToolDispatcher(
            registry=self.tool_registry,
            permission_manager=self.permission_manager,
            confirm_callback=confirm_callback,
            async_confirm_callback=async_confirm_callback,
        )

    def _init_session(self) -> None:
        self.conversation.create_session("JARVIS Session")

    # ---- conversation scoping ----

    def _ensure_user_session(self, user_id: str) -> str:
        session_id = self._user_sessions.get(user_id)
        if session_id and self.conversation.load_session(session_id):
            return session_id
        session_id = self.conversation.create_session(f"user:{user_id}")
        self._user_sessions[user_id] = session_id
        return session_id

    def get_session_ids(self) -> dict[str, str]:
        return dict(self._user_sessions)

    # ---- accessors ----

    def get_active_personality(self) -> str:
        p = self.personality_manager.get_active()
        return p.name if p else "jarvis"

    def get_system_prompt(self, user_id: str = "default") -> str:
        p = self.personality_manager.get_active()
        base = p.system_prompt if p else "You are JARVIS, a helpful AI assistant."
        if self.config.tool.enabled:
            base += (
                "\n\nYou have access to tools that can perform actions on the user's system "
                "(close apps, search files, execute commands, etc.). "
                "Use tools ONLY when the user explicitly asks you to perform an action. "
                "For general conversation, questions, or after successfully completing a task, "
                "respond naturally without calling any tools. "
                "Never call additional tools after a task is complete."
            )
        return self.conversation.build_system_prompt_with_memory(base, user_id=user_id)

    def switch_personality(self, name: str) -> bool:
        return self.personality_manager.set_active(name) is not None

    # ---- core ----

    async def chat(self, text: str, user_id: str = "default") -> str:
        self._ensure_llm()
        llm = self.llm
        if llm is None:
            raise RuntimeError("LLM not initialized.")
        self._ensure_user_session(user_id)
        self.conversation.add_message(LLMMessage(role="user", content=text))
        messages = self.conversation.get_history()
        system_prompt = self.get_system_prompt(user_id=user_id)

        if self.tool_dispatcher and self.config.tool.enabled:
            response = await self.tool_dispatcher.chat_with_tools(
                llm=llm,
                messages=messages,
                system_prompt=system_prompt,
                max_tool_rounds=self.config.tool.max_tool_rounds,
            )
        else:
            response = await llm.chat(messages, system_prompt=system_prompt)

        self.conversation.add_message(LLMMessage(role="assistant", content=response.content or ""))
        return response.content or "(no response)"

    async def health_report(self) -> dict:
        if not self.service_manager:
            return {}
        return await self.service_manager.health_report()

    def get_voice_for_active(self) -> str:
        return self.personality_manager.get_sarvam_voice()

    async def cleanup(self) -> None:
        if self.llm:
            try:
                await self.llm.close()
            except Exception:
                pass
        if self.service_manager:
            try:
                await self.service_manager.close()
            except Exception:
                pass
        self.conversation.close()
        self.memory_manager.close()
