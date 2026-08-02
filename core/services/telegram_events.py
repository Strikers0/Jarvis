from __future__ import annotations

import logging
from typing import Any, Optional

from core.services.telegram_confirmation import ConfirmationManager
from core.services.telegram_models import TelegramInboundMessage
from core.session import JarvisSession

logger = logging.getLogger(__name__)


class TelegramEventHandler:
    """Inbound NewMessage handler for Telegram.

    Gates on the allow-list, resolves inline confirmations, routes slash
    commands, and forwards everything else to the shared JarvisSession runtime.
    """

    def __init__(
        self,
        service: Any,
        session: JarvisSession,
        owner_chat_id: int = 0,
        voice_processor: Any = None,
        confirmation_manager: Optional[ConfirmationManager] = None,
    ):
        self.service = service
        self.session = session
        self.owner_chat_id = owner_chat_id
        self.voice_processor = voice_processor
        self.confirmation_manager = confirmation_manager

    async def handle(self, event: Any) -> None:
        self_user_id = await self._get_self_user_id()
        message = TelegramInboundMessage.from_telethon_event(event, self_user_id)
        if message is None:
            return

        if self.service.was_sent_by_us(message.message_id):
            return

        if not self.service.is_allowed_user(message.sender_id):
            logger.info(
                "Ignoring message from unauthorized user %s (chat %s)",
                message.sender_id,
                message.chat_id,
            )
            return

        if self.confirmation_manager is not None:
            resolved = await self.confirmation_manager.resolve(message.chat_id, message.text)
            if resolved:
                return

        try:
            if message.is_command:
                await self._handle_command(message)
            elif message.is_voice:
                await self._handle_voice(message)
            else:
                await self._handle_chat(message)
        except Exception as e:
            logger.exception("Telegram handler error")
            await self.service.send_message(
                message.recipient_id, f"Something went wrong: {e}"
            )

    async def _get_self_user_id(self) -> int:
        getter = getattr(self.service, "self_user_id", None)
        if getter is None:
            return 0
        try:
            return int(await getter())
        except Exception:
            return 0

    # ---- routing ----

    async def _handle_chat(self, message: TelegramInboundMessage) -> None:
        dispatcher = self.session.tool_dispatcher
        previous = dispatcher.async_confirm_callback if dispatcher else None
        if dispatcher and self.confirmation_manager is not None:
            dispatcher.async_confirm_callback = self._make_confirm_callback(message)
        try:
            reply = await self.session.chat(message.text, user_id=message.sender_id)
        finally:
            if dispatcher:
                dispatcher.async_confirm_callback = previous
        await self.service.send_message(message.recipient_id, reply)

    def _make_confirm_callback(self, message: TelegramInboundMessage):
        async def _confirm(tool_name: str, args: dict) -> bool:
            return await self.confirmation_manager.request(
                message.recipient_id, tool_name, args
            )

        return _confirm

    async def _handle_voice(self, message: TelegramInboundMessage) -> None:
        if self.voice_processor is None or not self.voice_processor.available:
            await self.service.send_message(
                message.recipient_id,
                "Voice notes are not supported in this build yet.",
            )
            return
        try:
            reply, voice_path = await self.voice_processor.process_event(
                message.raw, user_id=message.sender_id
            )
        except Exception as e:
            logger.exception("Telegram voice processing error")
            await self.service.send_message(
                message.recipient_id, f"Voice processing failed: {e}"
            )
            return
        if voice_path is not None:
            await self.service.send_voice(message.recipient_id, voice_path)
        else:
            await self.service.send_message(message.recipient_id, reply)

    # ---- commands ----

    async def _handle_command(self, message: TelegramInboundMessage) -> None:
        parts = message.text.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        dispatcher = self._command_map()
        handler = dispatcher.get(cmd)
        if handler is None:
            await self.service.send_message(
                message.recipient_id, f"Unknown command: {cmd}\nType /help for help."
            )
            return
        reply = await handler(message, arg)
        if reply:
            await self.service.send_message(message.recipient_id, reply)

    def _command_map(self) -> dict[str, Any]:
        return {
            "/help": self._cmd_help,
            "/start": self._cmd_help,
            "/personality": self._cmd_personality,
            "/voice": self._cmd_voice,
            "/services": self._cmd_services,
            "/notes": self._cmd_notes,
            "/todos": self._cmd_todos,
            "/remind": self._cmd_remind,
            "/model": self._cmd_model,
            "/memory": self._cmd_memory,
            "/clear": self._cmd_clear,
        }

    async def _cmd_help(self, message: TelegramInboundMessage, arg: str) -> str:
        return (
            "JARVIS commands:\n"
            "/help - this help\n"
            "/personality [name] - list or switch personality\n"
            "/voice [name] - show TTS voice for a personality\n"
            "/services - service health\n"
            "/notes - list notes\n"
            "/todos - list to-dos\n"
            "/remind - list reminders\n"
            "/model - current LLM model\n"
            "/memory - stored memories\n"
            "/clear - clear this conversation\n\n"
            "Anything else: just talk to me."
        )

    async def _cmd_personality(self, message: TelegramInboundMessage, arg: str) -> str:
        pm = self.session.personality_manager
        if not arg:
            names = ", ".join(pm.list_names())
            return f"Available personalities: {names}\nUse /personality <name> to switch."
        personality = pm.get(arg)
        if personality is None:
            return f"Personality '{arg}' not found. Type /personality to see all."
        pm.set_active(personality.name)
        return f"Switched to personality: {personality.name}"

    async def _cmd_voice(self, message: TelegramInboundMessage, arg: str) -> str:
        pm = self.session.personality_manager
        if arg:
            personality = pm.get(arg)
            if personality is None:
                return f"Personality '{arg}' not found."
            voice = pm.get_sarvam_voice(personality.name)
            return f"Voice for {personality.name}: {voice}"
        voice = pm.get_sarvam_voice()
        return f"Current personality voice: {voice}"

    async def _cmd_services(self, message: TelegramInboundMessage, arg: str) -> str:
        if self.session.service_manager is None:
            return "Services are disabled in config."
        report = await self.session.service_manager.health_report()
        if not report:
            return "No services configured."
        lines = []
        for name, health in report.items():
            status = "OK" if health.get("ok") else "ERROR"
            lines.append(f"• {name}: {status} — {health.get('detail', '')}")
        return "\n".join(lines)

    async def _cmd_notes(self, message: TelegramInboundMessage, arg: str) -> str:
        service = self._service("notes")
        if service is None:
            return "Notes service unavailable."
        notes = service.list_notes()
        return service.format_notes(notes)

    async def _cmd_todos(self, message: TelegramInboundMessage, arg: str) -> str:
        service = self._service("notes")
        if service is None:
            return "Notes service unavailable."
        todos = service.list_todos()
        return service.format_todos(todos)

    async def _cmd_remind(self, message: TelegramInboundMessage, arg: str) -> str:
        service = self._service("calendar")
        if service is None:
            return "Calendar service unavailable."
        reminders = service.list_reminders()
        return service.format_reminders(reminders)

    async def _cmd_model(self, message: TelegramInboundMessage, arg: str) -> str:
        return f"Model: {self.session.config.llm.model}"

    async def _cmd_memory(self, message: TelegramInboundMessage, arg: str) -> str:
        context = self.session.memory_manager.get_formatted_context(user_id=message.sender_id)
        return context or "No stored memories yet."

    async def _cmd_clear(self, message: TelegramInboundMessage, arg: str) -> str:
        session_id = self.session._user_sessions.get(message.sender_id)
        if session_id and self.session.conversation.load_session(session_id):
            self.session.conversation.clear_history()
            return "Conversation cleared."
        return "No conversation to clear."

    def _service(self, name: str):
        return self.session.service_manager.get(name) if self.session.service_manager else None
