from __future__ import annotations

from typing import Any

from core.tools.base import Tool, ToolResult


class SwitchPersonalityTool(Tool):
    def __init__(self, personality_manager: Any):
        self._manager = personality_manager
        super().__init__(
            name="switch_personality",
            description=(
                "Switch the assistant to a different personality. "
                "Available personalities: "
                + ", ".join(self._manager.list_names())
                + ". Call this when the user asks to change personality, "
                "become someone else, act as a girlfriend/boyfriend/teacher, etc."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the personality to switch to (e.g. 'girlfriend', 'jarvis', 'teacher').",
                    },
                },
                "required": ["name"],
            },
            permission_level="auto",
            category="personality",
        )

    async def execute(self, name: str) -> ToolResult:
        personality = self._manager.set_active(name)
        if not personality:
            return ToolResult(
                success=False,
                error=f"Unknown personality '{name}'. Available: {', '.join(self._manager.list_names())}",
            )
        return ToolResult(
            success=True,
            output=(
                f"Switched personality to '{personality.name}' ({personality.description}). "
                f"Respond from now on as {personality.name}."
            ),
        )


class PersonalityToolSet:
    def __init__(self, personality_manager: Any):
        self._manager = personality_manager

    def get_tools(self) -> list[Tool]:
        return [SwitchPersonalityTool(self._manager)]
