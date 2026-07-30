from __future__ import annotations

import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Any

from core.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)


class OpenFileTool(Tool):
    def __init__(self):
        super().__init__(
            name="open_file",
            description="Open a file or folder with the default application.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file or folder to open",
                    },
                },
                "required": ["path"],
            },
            permission_level="auto",
            category="system",
        )

    async def execute(self, path: str) -> ToolResult:
        try:
            resolved = Path(path).expanduser().resolve()
            if not resolved.exists():
                return ToolResult(success=False, error=f"Path does not exist: {resolved}")
            proc = await asyncio.create_subprocess_exec(
                "cmd", "/c", "start", "", str(resolved),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            await proc.wait()
            return ToolResult(success=True, output=f"Opened: {resolved}")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to open file: {e}")


class CreateFolderTool(Tool):
    def __init__(self):
        super().__init__(
            name="create_folder",
            description="Create a new folder at the specified path.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path where to create the folder",
                    },
                },
                "required": ["path"],
            },
            permission_level="auto",
            category="system",
        )

    async def execute(self, path: str) -> ToolResult:
        try:
            resolved = Path(path).expanduser().resolve()
            resolved.mkdir(parents=True, exist_ok=True)
            return ToolResult(success=True, output=f"Created folder: {resolved}")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to create folder: {e}")


class ListDirectoryTool(Tool):
    def __init__(self):
        super().__init__(
            name="list_directory",
            description="List files and folders in a directory.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to list",
                        "default": ".",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Optional file filter pattern (e.g. '*.txt', '*.py')",
                        "default": "",
                    },
                },
                "required": [],
            },
            permission_level="auto",
            category="system",
        )

    async def execute(self, path: str = ".", pattern: str = "") -> ToolResult:
        try:
            resolved = Path(path).expanduser().resolve()
            if not resolved.exists():
                return ToolResult(success=False, error=f"Directory does not exist: {resolved}")
            if not resolved.is_dir():
                return ToolResult(success=False, error=f"Not a directory: {resolved}")
            if pattern:
                items = list(resolved.glob(pattern))
            else:
                items = list(resolved.iterdir())
            dirs = [f"[DIR]  {p.name}" for p in items if p.is_dir()]
            files = [f"[FILE] {p.name} ({p.stat().st_size} bytes)" for p in items if p.is_file()]
            listing = dirs + files
            if not listing:
                return ToolResult(success=True, output=f"Directory is empty: {resolved}")
            output = f"Contents of {resolved}:\n" + "\n".join(listing[:100])
            return ToolResult(success=True, output=output, data={"items": [str(p) for p in items]})
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to list directory: {e}")


class SearchFilesTool(Tool):
    def __init__(self):
        super().__init__(
            name="search_files",
            description="Search for files matching a query in a directory. Uses Windows Search if available.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Filename or pattern to search for",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory to search in",
                        "default": "C:\\",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results",
                        "default": 20,
                    },
                },
                "required": ["query"],
            },
            permission_level="auto",
            category="system",
        )

    async def execute(self, query: str, path: str = "C:\\", max_results: int = 20) -> ToolResult:
        try:
            resolved = Path(path).expanduser().resolve()
            if not resolved.exists():
                return ToolResult(success=False, error=f"Path does not exist: {resolved}")
            results = []
            pattern = f"*{query}*" if "*" not in query else query
            for f in resolved.rglob(pattern):
                if len(results) >= max_results:
                    break
                try:
                    results.append(f"{f.parent.name}\\{f.name}")
                except (PermissionError, OSError):
                    continue
            if not results:
                return ToolResult(success=True, output=f"No files found matching '{query}' in {resolved}")
            output = f"Found {len(results)} files matching '{query}':\n" + "\n".join(results)
            return ToolResult(success=True, output=output, data={"results": results})
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to search files: {e}")


class GetSystemInfoTool(Tool):
    def __init__(self):
        super().__init__(
            name="get_system_info",
            description="Get basic system information (OS, CPU, memory, disk usage).",
            input_schema={"type": "object", "properties": {}},
            permission_level="auto",
            category="system",
        )

    async def execute(self) -> ToolResult:
        try:
            import platform
            import psutil
            info = {
                "os": platform.system() + " " + platform.release(),
                "hostname": platform.node(),
                "cpu_percent": psutil.cpu_percent(interval=1),
                "memory_percent": psutil.virtual_memory().percent,
                "memory_available_gb": round(psutil.virtual_memory().available / (1024**3), 2),
                "disk_percent": psutil.disk_usage("/").percent,
            }
            output = (
                f"OS: {info['os']}\n"
                f"Hostname: {info['hostname']}\n"
                f"CPU: {info['cpu_percent']}%\n"
                f"Memory: {info['memory_percent']}% used ({info['memory_available_gb']} GB available)\n"
                f"Disk: {info['disk_percent']}% used"
            )
            return ToolResult(success=True, output=output, data=info)
        except ImportError:
            import platform
            info = {
                "os": platform.system() + " " + platform.release(),
                "hostname": platform.node(),
            }
            output = f"OS: {info['os']}\nHostname: {info['hostname']}\n(Install psutil for more info)"
            return ToolResult(success=True, output=output, data=info)
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to get system info: {e}")


class ExecuteCommandTool(Tool):
    def __init__(self):
        super().__init__(
            name="execute_command",
            description="Execute a shell command and return its output. Use with caution.",
            input_schema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds",
                        "default": 30,
                    },
                },
                "required": ["command"],
            },
            permission_level="confirm",
            category="system",
        )

    async def execute(self, command: str, timeout: int = 30) -> ToolResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                "cmd", "/c", command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            output = stdout.decode().strip()
            error = stderr.decode().strip()
            if error:
                output += f"\nSTDERR: {error}" if output else error
            return ToolResult(
                success=proc.returncode == 0,
                output=output[:5000] or f"Command completed (exit code: {proc.returncode})",
                error=error if proc.returncode != 0 else "",
            )
        except asyncio.TimeoutError:
            return ToolResult(success=False, error=f"Command timed out after {timeout}s")
        except Exception as e:
            return ToolResult(success=False, error=f"Command execution failed: {e}")


class SystemToolSet:
    def get_tools(self) -> list[Tool]:
        return [
            OpenFileTool(),
            CreateFolderTool(),
            ListDirectoryTool(),
            SearchFilesTool(),
            GetSystemInfoTool(),
            ExecuteCommandTool(),
        ]
