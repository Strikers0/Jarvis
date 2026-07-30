from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from core.llm import LLMMessage

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    success: bool
    output: str = ""
    error: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def to_text(self) -> str:
        if self.success:
            return self.output or json.dumps(self.data, default=str)
        return f"Error: {self.error}"

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "data": self.data,
        }


PermissionLevel = str


class Tool(ABC):
    def __init__(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        permission_level: PermissionLevel = "confirm",
        category: str = "general",
    ):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.permission_level = permission_level
        self.category = category

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        ...

    def to_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            logger.warning("Overwriting existing tool: %s", tool.name)
        self._tools[tool.name] = tool

    def register_set(self, tool_set: Any) -> None:
        tools = tool_set.get_tools()
        for tool in tools:
            self.register(tool)

    def unregister(self, name: str) -> bool:
        return self._tools.pop(name, None) is not None

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())

    def list_by_category(self, category: str) -> list[Tool]:
        return [t for t in self._tools.values() if t.category == category]

    def get_openai_tools(self) -> list[dict[str, Any]]:
        return [t.to_openai_tool() for t in self._tools.values()]

    def get_tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)


class PermissionManager:
    def __init__(self, config: Optional[dict[str, str]] = None):
        self._overrides: dict[str, PermissionLevel] = {}
        self._audit_log: list[dict] = []
        if config:
            self.load_config(config)

    def load_config(self, config: dict[str, str]) -> None:
        self._overrides.update(config)

    def get_permission_level(self, tool_name: str, default: PermissionLevel = "confirm") -> PermissionLevel:
        return self._overrides.get(tool_name, default)

    def set_permission_level(self, tool_name: str, level: PermissionLevel) -> None:
        self._overrides[tool_name] = level

    def is_dangerous(self, tool_name: str) -> bool:
        dangerous_tools = {
            "close_app", "execute_command", "delete_file", "shutdown",
            "install_software", "modify_registry",
        }
        return tool_name in dangerous_tools

    def log_execution(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: ToolResult,
        user_id: str = "default",
    ) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool": tool_name,
            "args": args,
            "success": result.success,
            "output": result.output[:500] if result.output else "",
            "error": result.error[:500] if result.error else "",
            "user_id": user_id,
        }
        self._audit_log.append(entry)
        if not result.success:
            logger.warning("Tool %s failed: %s", tool_name, result.error)

    def get_audit_log(self, limit: int = 50) -> list[dict]:
        return self._audit_log[-limit:]

    def clear_audit_log(self) -> None:
        self._audit_log.clear()


class ToolDispatcher:
    def __init__(
        self,
        registry: ToolRegistry,
        permission_manager: PermissionManager,
        confirm_callback: Optional[Callable[[str, dict[str, Any]], bool]] = None,
    ):
        self.registry = registry
        self.permissions = permission_manager
        self.confirm_callback = confirm_callback

    async def dispatch(self, tool_name: str, args: dict[str, Any]) -> ToolResult:
        tool = self.registry.get(tool_name)
        if not tool:
            return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

        level = self.permissions.get_permission_level(tool_name, tool.permission_level)

        if level == "deny":
            return ToolResult(success=False, error=f"Tool '{tool_name}' is denied by permission settings")
        elif level == "confirm" and self.confirm_callback:
            confirmed = self.confirm_callback(tool_name, args)
            if not confirmed:
                return ToolResult(success=False, error=f"Tool '{tool_name}' execution cancelled by user")

        try:
            result = await tool.execute(**args)
        except Exception as e:
            result = ToolResult(success=False, error=str(e))

        self.permissions.log_execution(tool_name, args, result)
        return result

    async def process_llm_tool_calls(
        self,
        tool_calls: list[dict],
    ) -> list[dict]:
        results = []
        for tc in tool_calls:
            tool_name = tc.get("function", {}).get("name", "")
            try:
                args = json.loads(tc.get("function", {}).get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}
            result = await self.dispatch(tool_name, args)
            results.append({
                "role": "tool",
                "tool_call_id": tc.get("id", ""),
                "content": result.to_text(),
            })
        return results

    async def chat_with_tools(
        self,
        llm: Any,
        messages: list[LLMMessage],
        system_prompt: str,
        max_tool_rounds: int = 5,
    ) -> LLMMessage:
        current_messages = list(messages)
        for _ in range(max_tool_rounds):
            response = await llm.chat(
                current_messages,
                system_prompt=system_prompt,
                tools=self.registry.get_openai_tools(),
            )

            if not response.tool_calls:
                return response

            assistant_msg = LLMMessage(
                role="assistant",
                content=response.content or "",
                tool_calls=response.tool_calls,
            )
            current_messages.append(assistant_msg)

            tool_results = await self.process_llm_tool_calls(response.tool_calls)
            for tr in tool_results:
                current_messages.append(LLMMessage(
                    role=tr["role"],
                    content=tr["content"],
                    tool_call_id=tr["tool_call_id"],
                ))

        final = await llm.chat(
            current_messages,
            system_prompt=system_prompt,
        )
        return final
