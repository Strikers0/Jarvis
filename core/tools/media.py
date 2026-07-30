from __future__ import annotations

import asyncio
import logging
import subprocess

from core.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)


class PlayYouTubeTool(Tool):
    def __init__(self):
        super().__init__(
            name="play_youtube",
            description="Search and play a YouTube video or open a YouTube URL in the browser.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query or YouTube URL",
                    },
                },
                "required": ["query"],
            },
            permission_level="auto",
            category="media",
        )

    async def execute(self, query: str) -> ToolResult:
        if query.startswith(("http://", "https://")) and "youtube.com" in query:
            url = query
        else:
            url = f"https://www.youtube.com/results?search_query={query}"
        try:
            proc = await asyncio.create_subprocess_exec(
                "cmd", "/c", "start", "", url,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            await proc.wait()
            return ToolResult(success=True, output=f"Opening YouTube: {query}")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to open YouTube: {e}")


class MediaControlTool(Tool):
    def __init__(self):
        super().__init__(
            name="control_media",
            description="Control media playback (play/pause/next/previous/stop). Uses keyboard media keys.",
            input_schema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["play", "pause", "play_pause", "next", "previous", "stop"],
                        "description": "Media control action",
                    },
                },
                "required": ["action"],
            },
            permission_level="auto",
            category="media",
        )

    async def execute(self, action: str) -> ToolResult:
        key_map = {
            "play": "playpause",
            "pause": "playpause",
            "play_pause": "playpause",
            "next": "nexttrack",
            "previous": "prevtrack",
            "stop": "stop",
        }
        key = key_map.get(action)
        if not key:
            return ToolResult(success=False, error=f"Unknown media action: {action}")
        try:
            import pyautogui
            pyautogui.press(key)
            return ToolResult(success=True, output=f"Media action '{action}' executed")
        except ImportError:
            return ToolResult(success=False, error="pyautogui is not installed")
        except Exception as e:
            return ToolResult(success=False, error=f"Media control failed: {e}")


class PlayMusicTool(Tool):
    def __init__(self):
        super().__init__(
            name="play_music",
            description="Play music by opening a YouTube Music or Spotify search.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Song name or artist to play",
                    },
                    "service": {
                        "type": "string",
                        "enum": ["youtube", "spotify"],
                        "description": "Music service to use",
                        "default": "youtube",
                    },
                },
                "required": ["query"],
            },
            permission_level="auto",
            category="media",
        )

    async def execute(self, query: str, service: str = "youtube") -> ToolResult:
        if service == "spotify":
            url = f"https://open.spotify.com/search/{query}"
        else:
            url = f"https://music.youtube.com/search?q={query}"
        try:
            proc = await asyncio.create_subprocess_exec(
                "cmd", "/c", "start", "", url,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            await proc.wait()
            return ToolResult(success=True, output=f"Opening {service} search for: {query}")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to open music service: {e}")


class MediaToolSet:
    def get_tools(self) -> list[Tool]:
        return [
            PlayYouTubeTool(),
            MediaControlTool(),
            PlayMusicTool(),
        ]
