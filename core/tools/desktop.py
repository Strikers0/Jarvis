from __future__ import annotations

import asyncio
import logging
import subprocess
from pathlib import Path

from core.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)


class OpenAppTool(Tool):
    def __init__(self):
        super().__init__(
            name="open_app",
            description="Launch an application by name. Searches Start Menu and PATH.",
            input_schema={
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "Name of the application to open (e.g. 'chrome', 'notepad', 'spotify')",
                    }
                },
                "required": ["app_name"],
            },
            permission_level="auto",
            category="desktop",
        )

    async def execute(self, app_name: str) -> ToolResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                "cmd", "/c", "start", "", app_name,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            await proc.wait()
            return ToolResult(success=True, output=f"Launched application: {app_name}")
        except FileNotFoundError:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "powershell", "-Command", f"Start-Process '{app_name}'",
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                await proc.wait()
                return ToolResult(success=True, output=f"Launched application: {app_name}")
            except Exception as e:
                return ToolResult(success=False, error=f"Failed to open '{app_name}': {e}")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to open '{app_name}': {e}")


class CloseAppTool(Tool):
    def __init__(self):
        super().__init__(
            name="close_app",
            description="Close an application by process name.",
            input_schema={
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "Process name to close (e.g. 'chrome', 'notepad')",
                    },
                    "force": {
                        "type": "boolean",
                        "description": "Force kill the process",
                        "default": False,
                    },
                },
                "required": ["app_name"],
            },
            permission_level="confirm",
            category="desktop",
        )

    async def execute(self, app_name: str, force: bool = False) -> ToolResult:
        try:
            args = ["taskkill", "/im", f"{app_name}.exe"]
            if force:
                args.append("/f")
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
            if proc.returncode == 0:
                return ToolResult(success=True, output=f"Closed application: {app_name}")
            return ToolResult(success=False, error=stderr.decode().strip() or f"Failed to close {app_name}")
        except asyncio.TimeoutError:
            return ToolResult(success=False, error=f"Timed out trying to close {app_name}. The app may not respond to close requests.")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to close '{app_name}': {e}")


class TypeTextTool(Tool):
    def __init__(self):
        super().__init__(
            name="type_text",
            description="Simulate typing text into the currently focused window.",
            input_schema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Text to type",
                    },
                    "interval": {
                        "type": "number",
                        "description": "Seconds between keystrokes",
                        "default": 0.05,
                    },
                },
                "required": ["text"],
            },
            permission_level="auto",
            category="desktop",
        )

    async def execute(self, text: str, interval: float = 0.05) -> ToolResult:
        try:
            import pyautogui
            pyautogui.write(text, interval=interval)
            return ToolResult(success=True, output=f"Typed text ({len(text)} characters)")
        except ImportError:
            return ToolResult(success=False, error="pyautogui is not installed. Install with: pip install pyautogui")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to type text: {e}")


class PressKeyTool(Tool):
    def __init__(self):
        super().__init__(
            name="press_key",
            description="Press a keyboard key or key combination (e.g. 'enter', 'ctrl+c', 'alt+tab').",
            input_schema={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Key or key combination to press",
                    },
                },
                "required": ["key"],
            },
            permission_level="auto",
            category="desktop",
        )

    async def execute(self, key: str) -> ToolResult:
        try:
            import pyautogui
            if "+" in key:
                parts = key.lower().split("+")
                modifiers = [p.strip() for p in parts[:-1]]
                main_key = parts[-1].strip()
                pyautogui.hotkey(*modifiers, main_key)
            else:
                pyautogui.press(key)
            return ToolResult(success=True, output=f"Pressed key: {key}")
        except ImportError:
            return ToolResult(success=False, error="pyautogui is not installed")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to press key: {e}")


class ClickTool(Tool):
    def __init__(self):
        super().__init__(
            name="click",
            description="Click at specified screen coordinates or click with element description.",
            input_schema={
                "type": "object",
                "properties": {
                    "x": {
                        "type": "integer",
                        "description": "X coordinate on screen. Use -1 to use current mouse position.",
                        "default": -1,
                    },
                    "y": {
                        "type": "integer",
                        "description": "Y coordinate on screen. Use -1 to use current mouse position.",
                        "default": -1,
                    },
                    "button": {
                        "type": "string",
                        "enum": ["left", "right", "middle"],
                        "description": "Mouse button to click",
                        "default": "left",
                    },
                    "clicks": {
                        "type": "integer",
                        "description": "Number of clicks (1=single, 2=double)",
                        "default": 1,
                    },
                },
                "required": [],
            },
            permission_level="auto",
            category="desktop",
        )

    async def execute(self, x: int = -1, y: int = -1, button: str = "left", clicks: int = 1) -> ToolResult:
        try:
            import pyautogui
            if x >= 0 and y >= 0:
                pyautogui.click(x=x, y=y, button=button, clicks=clicks)
                return ToolResult(success=True, output=f"Clicked at ({x}, {y}) with {button} button")
            pyautogui.click(button=button, clicks=clicks)
            return ToolResult(success=True, output=f"Clicked at current position with {button} button")
        except ImportError:
            return ToolResult(success=False, error="pyautogui is not installed")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to click: {e}")


class ScreenshotTool(Tool):
    def __init__(self):
        super().__init__(
            name="screenshot",
            description="Capture a screenshot of the entire screen or a region.",
            input_schema={
                "type": "object",
                "properties": {
                    "save_path": {
                        "type": "string",
                        "description": "Path to save the screenshot. Uses temp file if not provided.",
                        "default": "",
                    },
                },
                "required": [],
            },
            permission_level="auto",
            category="desktop",
        )

    async def execute(self, save_path: str = "") -> ToolResult:
        try:
            import pyautogui
            if not save_path:
                import tempfile
                save_path = str(Path(tempfile.gettempdir()) / f"jarvis_screenshot_{datetime.now():%Y%m%d_%H%M%S}.png")
            from datetime import datetime
            screenshot = pyautogui.screenshot()
            screenshot.save(save_path)
            return ToolResult(success=True, output=f"Screenshot saved to {save_path}", data={"path": save_path})
        except ImportError:
            return ToolResult(success=False, error="pyautogui is not installed")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to take screenshot: {e}")


class GetVolumeTool(Tool):
    def __init__(self):
        super().__init__(
            name="get_volume",
            description="Get current system volume level (0-100).",
            input_schema={"type": "object", "properties": {}},
            permission_level="auto",
            category="desktop",
        )

    async def execute(self) -> ToolResult:
        try:
            import pycaw.pycaw
            from pycaw.api.endpoint import Endpoint
            volume = Endpoint().get_master_volume()
            return ToolResult(success=True, output=f"Current volume: {int(volume * 100)}%", data={"volume": int(volume * 100)})
        except ImportError:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "powershell", "-Command",
                    "(Get-AudioDevice -Playback).Volume",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                stdout, _ = await proc.communicate()
                vol = stdout.decode().strip()
                return ToolResult(success=True, output=f"Current volume: {vol}%", data={"volume": vol})
            except Exception:
                return ToolResult(success=False, error="Could not read volume level. Install pycaw: pip install pycaw")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to get volume: {e}")


class SetVolumeTool(Tool):
    def __init__(self):
        super().__init__(
            name="set_volume",
            description="Set system volume level (0-100).",
            input_schema={
                "type": "object",
                "properties": {
                    "level": {
                        "type": "integer",
                        "description": "Volume level 0-100",
                        "minimum": 0,
                        "maximum": 100,
                    },
                },
                "required": ["level"],
            },
            permission_level="auto",
            category="desktop",
        )

    async def execute(self, level: int) -> ToolResult:
        try:
            from pycaw.pycaw import AudioUtilities
            sessions = AudioUtilities.GetAllSessions()
            for session in sessions:
                if session.Process and session.Process.name():
                    volume = session.SimpleAudioVolume
                    if volume:
                        volume.SetMasterVolume(level / 100.0, None)
            return ToolResult(success=True, output=f"Volume set to {level}%")
        except ImportError:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "powershell", "-Command",
                    f"Set-AudioDevice -Volume {level}",
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                await proc.wait()
                return ToolResult(success=True, output=f"Volume set to {level}%")
            except Exception:
                return ToolResult(success=False, error="Could not set volume. Install pycaw: pip install pycaw")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to set volume: {e}")


class GetClipboardTool(Tool):
    def __init__(self):
        super().__init__(
            name="get_clipboard",
            description="Get text from the system clipboard.",
            input_schema={"type": "object", "properties": {}},
            permission_level="auto",
            category="desktop",
        )

    async def execute(self) -> ToolResult:
        try:
            import pyperclip
            text = pyperclip.paste()
            return ToolResult(success=True, output=f"Clipboard content: {text[:1000]}", data={"text": text[:5000]})
        except ImportError:
            return ToolResult(success=False, error="pyperclip is not installed. Install with: pip install pyperclip")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to read clipboard: {e}")


class SetClipboardTool(Tool):
    def __init__(self):
        super().__init__(
            name="set_clipboard",
            description="Set text on the system clipboard.",
            input_schema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Text to copy to clipboard",
                    },
                },
                "required": ["text"],
            },
            permission_level="auto",
            category="desktop",
        )

    async def execute(self, text: str) -> ToolResult:
        try:
            import pyperclip
            pyperclip.copy(text)
            return ToolResult(success=True, output=f"Copied to clipboard ({len(text)} characters)")
        except ImportError:
            return ToolResult(success=False, error="pyperclip is not installed")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to set clipboard: {e}")


class FocusWindowTool(Tool):
    def __init__(self):
        super().__init__(
            name="focus_window",
            description="Bring a window to focus by title or process name.",
            input_schema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Window title or process name to focus",
                    },
                },
                "required": ["title"],
            },
            permission_level="auto",
            category="desktop",
        )

    async def execute(self, title: str) -> ToolResult:
        try:
            import pygetwindow as gw
            windows = gw.getWindowsWithTitle(title)
            if not windows:
                windows = [w for w in gw.getAllWindows() if title.lower() in w.title.lower()]
            if windows:
                windows[0].activate()
                return ToolResult(success=True, output=f"Focused window: {windows[0].title}")
            return ToolResult(success=False, error=f"No window found matching '{title}'")
        except ImportError:
            return ToolResult(success=False, error="pygetwindow is not installed. Install with: pip install pygetwindow")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to focus window: {e}")


class DesktopAutomationToolSet:
    def get_tools(self) -> list[Tool]:
        return [
            OpenAppTool(),
            CloseAppTool(),
            TypeTextTool(),
            PressKeyTool(),
            ClickTool(),
            ScreenshotTool(),
            GetVolumeTool(),
            SetVolumeTool(),
            GetClipboardTool(),
            SetClipboardTool(),
            FocusWindowTool(),
        ]
