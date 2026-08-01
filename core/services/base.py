from __future__ import annotations

import inspect
import logging
from abc import ABC, abstractmethod
from typing import Any, Callable

from core.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)


class Service(ABC):
    """Base class for external integrations (email, calendar, calling, etc.)."""

    name: str = "base"
    description: str = "Base service"

    @abstractmethod
    async def health_check(self) -> dict:
        """Return a health status dict, e.g. {"ok": True, "detail": "..."}."""

    def get_tools(self) -> list[Tool]:
        return []

    def is_configured(self) -> bool:
        return True

    async def close(self) -> None:
        pass


def service_tool(
    name: str,
    description: str,
    parameters: dict[str, Any],
    handler: Callable[..., Any],
    category: str = "services",
    permission_level: str = "confirm",
) -> Tool:
    """Wrap an async service method into a Tool."""

    class _ServiceTool(Tool):
        def __init__(self):
            super().__init__(
                name=name,
                description=description,
                input_schema=parameters,
                permission_level=permission_level,
                category=category,
            )

        async def execute(self, **kwargs: Any) -> ToolResult:
            try:
                result = handler(**kwargs)
                if inspect.isawaitable(result):
                    result = await result
            except Exception as e:
                logger.exception("Service tool %s failed", name)
                return ToolResult(success=False, error=str(e))
            if isinstance(result, ToolResult):
                return result
            return ToolResult(success=True, output=str(result))

    return _ServiceTool()
