from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ReminderPoller:
    """Background task that pushes due reminders to the owner chat.

    Polls `calendar.check_due_reminders()` every `interval` seconds and sends
    each due reminder to the configured owner chat (or allow-listed chats).
    """

    def __init__(
        self,
        calendar_service: Any,
        service: Any,
        owner_chat_id: int = 0,
        allowed_users: Optional[list[int]] = None,
        interval: float = 30.0,
    ):
        self.calendar = calendar_service
        self.service = service
        self.owner_chat_id = owner_chat_id
        self.allowed_users = list(allowed_users or [])
        self.interval = interval
        self._task: Optional[asyncio.Task] = None
        self._running = False

    @property
    def enabled(self) -> bool:
        return (
            self.calendar is not None
            and getattr(self.calendar, "reminders_enabled", True)
            and self.service is not None
            and bool(self.owner_chat_id)
        )

    def _target_chats(self) -> list[int]:
        chats = {int(self.owner_chat_id)}
        if self.allowed_users:
            chats.update(int(u) for u in self.allowed_users if u)
        return [c for c in chats if c]

    async def poll_once(self) -> list[dict]:
        """Check for due reminders and push them. Returns the pushed reminders."""
        if not self.enabled:
            return []
        try:
            due = self.calendar.check_due_reminders()
        except Exception as e:
            logger.warning("Reminder poll failed: %s", e)
            return []
        if not due:
            return []
        chats = self._target_chats()
        for r in due:
            text = f"⏰ Reminder: {r['title']}"
            for chat in chats:
                try:
                    ok = await self.service.send_message(str(chat), text)
                    if not ok:
                        logger.warning("Failed to push reminder %s to chat %s", r["id"], chat)
                except Exception as e:
                    logger.warning("Reminder push error: %s", e)
        return due

    async def _loop(self) -> None:
        while self._running:
            try:
                await self.poll_once()
            except Exception as e:
                logger.exception("Reminder loop error: %s", e)
            await asyncio.sleep(self.interval)

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
