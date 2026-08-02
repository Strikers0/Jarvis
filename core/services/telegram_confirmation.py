from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class ConfirmationManager:
    """Inline chat confirmations.

    When a tool needs confirmation, `request()` sends a yes/no prompt to the
    chat and waits for the user's reply. The event handler resolves the pending
    confirmation via `resolve()` when the next inbound message from that chat
    arrives (or `cancel_all` on shutdown).
    """

    YES_WORDS = {"yes", "y", "ok", "okay", "allow", "confirm", "sure", "yeah"}

    def __init__(self, service: Any, timeout: float = 120.0):
        self.service = service
        self.timeout = timeout
        self._pending: dict[str, asyncio.Future] = {}

    async def request(self, chat_id: str, tool_name: str, args: dict[str, Any]) -> bool:
        prompt = (
            f"Allow this action?\n"
            f"Tool: {tool_name}\n"
            f"Arguments: {json.dumps(args, default=str)[:200]}\n\n"
            f"Reply yes or no."
        )
        future = asyncio.get_event_loop().create_future()
        self._pending[chat_id] = future
        try:
            await self.service.send_message(chat_id, prompt)
        except Exception:
            self._pending.pop(chat_id, None)
            raise
        try:
            result = await asyncio.wait_for(future, timeout=self.timeout)
            return bool(result)
        except asyncio.TimeoutError:
            await self.service.send_message(
                chat_id, "Confirmation timed out; action cancelled."
            )
            return False
        finally:
            self._pending.pop(chat_id, None)

    def has_pending(self, chat_id: str) -> bool:
        future = self._pending.get(chat_id)
        return future is not None and not future.done()

    async def resolve(self, chat_id: str, text: str) -> bool:
        """Resolve a pending confirmation for chat_id. Returns True if handled."""
        future = self._pending.get(chat_id)
        if future is None or future.done():
            return False
        future.set_result(text.strip().lower() in self.YES_WORDS)
        return True

    def cancel_all(self) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_result(False)
        self._pending.clear()
