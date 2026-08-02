from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from core.llm import LLMMessage
from core.session import JarvisSession

console = Console()


def print_header(personality_name: str, model: str) -> None:
    console.clear()
    title = Text("JARVIS - Intelligent Personal AI Assistant", style="bold cyan")
    subtitle = Text(f"Personality: {personality_name} | Model: {model}", style="dim")
    console.print(title)
    console.print(subtitle)
    console.print("─" * console.width)


def print_welcome() -> None:
    welcome = Panel(
        "[bold cyan]JARVIS[/bold cyan] is ready. Type your message or use commands:\n\n"
        "  [bold]/personality[/bold] <name>  - Switch personality\n"
        "  [bold]/voice[/bold] [name]        - Choose a TTS voice for a personality\n"
        "  [bold]/history[/bold]              - Show conversation history\n"
        "  [bold]/clear[/bold]                - Clear current conversation\n"
        "  [bold]/sessions[/bold]             - List all sessions\n"
        "  [bold]/save[/bold]                 - Export current session to JSON\n"
        "  [bold]/load[/bold] <id>            - Load a session\n"
        "  [bold]/model[/bold]                - Show current model\n"
        "  [bold]/memory[/bold]               - Show stored memories\n"
        "  [bold]/tools[/bold]                 - List available tools\n"
        "  [bold]/audit[/bold]                - Show tool execution audit log\n"
        "  [bold]/services[/bold]             - Show service health status\n"
        "  [bold]/notes[/bold]                - List notes\n"
        "  [bold]/todos[/bold]                - List to-do items\n"
        "  [bold]/remind[/bold]               - List upcoming reminders\n"
        "  [bold]/help[/bold]                 - Show this help\n"
        "  [bold]/exit[/bold]                 - Exit JARVIS",
        title="Help",
        border_style="cyan",
    )
    console.print(welcome)


class JARVISCLI:
    def __init__(self):
        self.session = JarvisSession(confirm_callback=self._confirm_tool_execution)
        if not self.config.tool.enabled:
            console.print("[dim]Tool use is disabled in config.[/dim]")
        else:
            console.print(f"[dim]Loaded {len(self.tool_registry)} tools[/dim]")
        self._init_llm()

    def __getattr__(self, name):
        session = self.__dict__.get("session")
        if session is not None:
            return getattr(session, name)
        raise AttributeError(name)

    def _init_llm(self) -> None:
        try:
            self.session._ensure_llm()
        except ValueError as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            console.print("[yellow]Please set the appropriate API key in your environment or .env file.[/yellow]")
            sys.exit(1)

    def _confirm_tool_execution(self, tool_name: str, args: dict) -> bool:
        import json
        args_str = json.dumps(args, indent=2)
        panel = Panel(
            f"[bold yellow]Tool:[/bold yellow] {tool_name}\n"
            f"[bold yellow]Arguments:[/bold yellow]\n{args_str}",
            title="Confirm Action",
            border_style="yellow",
        )
        console.print(panel)
        result = Prompt.ask("Allow this action?", choices=["y", "n", "a"], default="n")
        if result.lower() == "a":
            self.permission_manager.set_permission_level(tool_name, "auto")
            console.print(f"[green]Set '{tool_name}' permission to auto (always allow).[/green]")
            return True
        return result.lower() == "y"

    def _get_active_personality(self) -> str:
        p = self.personality_manager.get_active()
        return p.name if p else "jarvis"

    def _get_system_prompt(self) -> str:
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
        return self.conversation.build_system_prompt_with_memory(base)

    async def run(self) -> None:
        print_header(self._get_active_personality(), self.config.llm.model)
        print_welcome()

        while True:
            try:
                user_input = Prompt.ask("\n[bold green]You[/bold green]")
            except (EOFError, KeyboardInterrupt):
                console.print("\n[yellow]Goodbye![/yellow]")
                break

            if not user_input.strip():
                continue

            if user_input.startswith("/"):
                await self._handle_command(user_input)
                continue

            await self._handle_message(user_input)
            self._check_due_reminders()

        await self.cleanup()

    async def _handle_command(self, command: str) -> None:
        parts = command.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "/exit":
            console.print("[yellow]Goodbye![/yellow]")
            sys.exit(0)

        elif cmd == "/help":
            print_welcome()

        elif cmd == "/personality":
            await self._switch_personality(arg)

        elif cmd == "/voice":
            self._choose_voice(arg)

        elif cmd == "/history":
            self._show_history()

        elif cmd == "/clear":
            self.conversation.clear_history()
            console.print("[green]Conversation cleared.[/green]")

        elif cmd == "/sessions":
            self._list_sessions()

        elif cmd == "/save":
            self._save_session()

        elif cmd == "/load":
            self._load_session(arg)

        elif cmd == "/model":
            console.print(f"[cyan]Current model:[/cyan] {self.config.llm.model}")
            if self.llm:
                total = self.llm.usage.total_tokens
                cost = self.llm.usage.cost
                console.print(f"[dim]Tokens used: {total} | Cost: ${cost:.6f}[/dim]")

        elif cmd == "/memory":
            self._show_memory()

        elif cmd == "/tools":
            self._list_tools()

        elif cmd == "/audit":
            self._show_audit_log()

        elif cmd == "/services":
            await self._show_services()

        elif cmd == "/notes":
            self._show_notes()

        elif cmd == "/todos":
            self._show_todos()

        elif cmd == "/remind":
            self._show_reminders()

        else:
            console.print(f"[red]Unknown command:[/red] {cmd}")
            console.print("Type [bold]/help[/bold] for available commands.")

    async def _switch_personality(self, name: str) -> None:
        if not name:
            table = Table(title="Available Personalities")
            table.add_column("Name", style="cyan")
            table.add_column("Gender", style="dim")
            table.add_column("Description")
            for p in self.personality_manager.list():
                table.add_row(p.name, p.gender, p.description)
            console.print(table)
            return

        personality = self.personality_manager.get(name)
        if not personality:
            genders = {p.gender for p in self.personality_manager.list()}
            if name.lower() in genders:
                matches = [p for p in self.personality_manager.list() if p.gender == name.lower()]
                table = Table(title=f"Available {name.capitalize()} Personalities")
                table.add_column("Name", style="cyan")
                table.add_column("Description")
                for p in matches:
                    table.add_row(p.name, p.description)
                console.print(table)
                return
            console.print(f"[red]Personality '{name}' not found.[/red]")
            console.print("Type [bold]/personality[/bold] to see all available personalities.")
            return

        preview = Panel(
            f"[bold]{personality.name.capitalize()}[/bold]\n"
            f"[dim]{personality.gender} | {personality.traits.tone} | {personality.traits.formality}[/dim]\n\n"
            f"{personality.description}",
            title="Preview",
            border_style="cyan",
        )
        console.print(preview)
        confirm = Prompt.ask("Switch to this personality?", choices=["y", "n"], default="y")
        if confirm.lower() == "y":
            self.personality_manager.set_active(personality.name)
            console.print(f"[green]Switched to personality:[/green] {personality.name}")
            print_header(personality.name.replace("_", " ").title(), self.config.llm.model)
        else:
            console.print("[dim]Personality not changed.[/dim]")

    def _choose_voice(self, name: str) -> None:
        if not name:
            personality = self.personality_manager.get_active()
            if personality is None:
                console.print("[red]No active personality.[/red]")
                return
        else:
            personality = self.personality_manager.get(name)
            if personality is None:
                console.print(f"[red]Personality '{name}' not found.[/red]")
                console.print("Type [bold]/personality[/bold] to see all available personalities.")
                return

        from voice.sarvam_voices import voices_for_gender

        voices = voices_for_gender(personality.gender)
        current = self.personality_manager.get_sarvam_voice(personality.name)

        console.print(Panel(
            f"[bold]{personality.name.capitalize()}[/bold] ([dim]{personality.gender}[/dim])\n"
            f"Current voice: [cyan]{current}[/cyan]",
            title="Choose TTS Voice",
            border_style="cyan",
        ))

        for i, voice in enumerate(voices, start=1):
            marker = "  > " if voice == current else "    "
            console.print(f"{marker}[bold]{i:2}[/bold]. {voice}")

        choice = Prompt.ask(
            "Select a voice (number, or Enter to keep current)",
            default="",
        ).strip()
        if not choice:
            console.print("[dim]Voice not changed.[/dim]")
            return

        try:
            index = int(choice)
            if 1 <= index <= len(voices):
                selected = voices[index - 1]
            else:
                console.print("[red]Invalid number.[/red]")
                return
        except ValueError:
            selected = choice.lower()

        if selected not in voices:
            console.print(
                f"[red]'{selected}' is not available for {personality.gender} personalities.[/red]"
            )
            return

        if self.personality_manager.set_sarvam_voice(personality.name, selected):
            console.print(
                f"[green]Voice set:[/green] {personality.name} -> [cyan]{selected}[/cyan]"
            )
            console.print("[dim]Use live voice mode (python -m cli.voice_live) to hear it.[/dim]")
        else:
            console.print(f"[red]Could not set voice '{selected}'.[/red]")

    def _show_history(self) -> None:
        messages = self.conversation.get_history()
        if not messages:
            console.print("[dim]No conversation history.[/dim]")
            return
        for msg in messages:
            style = "green" if msg.role == "user" else "cyan"
            if msg.role == "user":
                label = "You"
            else:
                label = self._get_active_personality().replace("_", " ").title()
            console.print(f"[bold {style}]{label}:[/bold {style}] {msg.content[:200]}")

    def _show_memory(self) -> None:
        context = self.memory_manager.get_formatted_context()
        if not context:
            console.print("[dim]No memories stored yet.[/dim]")
            return
        panel = Panel(
            context,
            title="Stored Memories",
            border_style="cyan",
        )
        console.print(panel)

    def _list_sessions(self) -> None:
        sessions = self.conversation.list_sessions()
        if not sessions:
            console.print("[dim]No saved sessions.[/dim]")
            return
        table = Table(title="Sessions")
        table.add_column("ID", style="cyan")
        table.add_column("Name")
        table.add_column("Messages")
        table.add_column("Last Updated")
        current = self.conversation.get_current_session_id()
        for s in sessions:
            marker = " *" if s["id"] == current else ""
            table.add_row(
                s["id"][:8] + marker,
                s["name"],
                str(len(self.conversation.get_history())),
                s["updated_at"][:19] if s["updated_at"] else "",
            )
        console.print(table)

    def _save_session(self) -> None:
        session_id = self.conversation.get_current_session_id()
        if not session_id:
            console.print("[red]No active session.[/red]")
            return
        data = self.conversation.export_session(session_id)
        if not data:
            console.print("[red]Failed to export session.[/red]")
            return
        path = Path.cwd() / f"session_{session_id[:8]}.json"
        import json
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        console.print(f"[green]Session saved to:[/green] {path}")

    def _load_session(self, session_id: str) -> None:
        if not session_id:
            self._list_sessions()
            console.print("[yellow]Usage: /load <session_id>[/yellow]")
            return
        full_id = self._find_session_id(session_id)
        if not full_id:
            console.print(f"[red]Session '{session_id}' not found.[/red]")
            return
        if self.conversation.load_session(full_id):
            console.print(f"[green]Loaded session:[/green] {full_id[:8]}")
        else:
            console.print("[red]Failed to load session.[/red]")

    def _find_session_id(self, partial: str) -> Optional[str]:
        for s in self.conversation.list_sessions():
            if s["id"].startswith(partial):
                return s["id"]
        return None

    def _list_tools(self) -> None:
        tools = self.tool_registry.list_tools()
        if not tools:
            console.print("[dim]No tools available.[/dim]")
            return
        table = Table(title="Available Tools")
        table.add_column("Name", style="cyan")
        table.add_column("Category", style="dim")
        table.add_column("Description")
        table.add_column("Permission")
        for t in tools:
            level = self.permission_manager.get_permission_level(t.name, t.permission_level)
            level_str = {"auto": "[green]auto[/green]", "confirm": "[yellow]confirm[/yellow]", "deny": "[red]deny[/red]"}.get(level, level)
            dangerous = " ⚠" if self.permission_manager.is_dangerous(t.name) else ""
            table.add_row(t.name + dangerous, t.category, t.description[:60], level_str)
        console.print(table)
        console.print("[dim]⚠ = potentially dangerous operation[/dim]")

    def _show_audit_log(self) -> None:
        log = self.permission_manager.get_audit_log(20)
        if not log:
            console.print("[dim]No tool executions recorded yet.[/dim]")
            return
        table = Table(title="Tool Execution Audit Log (last 20)")
        table.add_column("Time", style="dim")
        table.add_column("Tool")
        table.add_column("Success")
        table.add_column("Output/Error")
        for entry in log:
            status = "[green]OK[/green]" if entry["success"] else "[red]FAIL[/red]"
            output = (entry["output"] or entry["error"] or "")[:60]
            table.add_row(
                entry["timestamp"][11:19],
                entry["tool"],
                status,
                output,
            )
        console.print(table)

    async def _show_services(self) -> None:
        if not self.service_manager:
            console.print("[dim]Services are disabled in config.[/dim]")
            return
        report = await self.service_manager.health_report()
        table = Table(title="Service Health")
        table.add_column("Service", style="cyan")
        table.add_column("Status")
        table.add_column("Detail")
        for name, health in report.items():
            status = "[green]OK[/green]" if health.get("ok") else "[red]ERROR[/red]"
            table.add_row(name, status, str(health.get("detail", ""))[:80])
        console.print(table)

    def _get_service(self, name: str):
        return self.service_manager.get(name) if self.service_manager else None

    def _show_notes(self) -> None:
        service = self._get_service("notes")
        if not service:
            console.print("[dim]Notes service unavailable.[/dim]")
            return
        notes = service.list_notes()
        console.print(Panel(service.format_notes(notes), title="Notes", border_style="cyan"))

    def _show_todos(self) -> None:
        service = self._get_service("notes")
        if not service:
            console.print("[dim]Notes service unavailable.[/dim]")
            return
        todos = service.list_todos()
        console.print(Panel(service.format_todos(todos), title="To-Do", border_style="cyan"))

    def _show_reminders(self) -> None:
        service = self._get_service("calendar")
        if not service:
            console.print("[dim]Calendar service unavailable.[/dim]")
            return
        reminders = service.list_reminders()
        console.print(Panel(service.format_reminders(reminders), title="Upcoming Reminders", border_style="cyan"))

    def _check_due_reminders(self) -> None:
        service = self._get_service("calendar")
        if not service or not service.reminders_enabled:
            return
        try:
            due = service.check_due_reminders()
        except Exception:
            return
        for r in due:
            panel = Panel(
                f"[bold]⏰ {r['title']}[/bold]",
                title="Reminder",
                border_style="yellow",
            )
            console.print(panel)

    async def _handle_message(self, user_input: str) -> None:
        if not self.llm:
            console.print("[red]LLM not initialized.[/red]")
            return

        user_message = LLMMessage(role="user", content=user_input)
        self.conversation.add_message(user_message)

        messages = self.conversation.get_history()
        system_prompt = self._get_system_prompt()

        try:
            if self.tool_dispatcher and self.config.tool.enabled:
                with console.status("[cyan]Processing with tools...[/cyan]", spinner="dots"):
                    response = await self.tool_dispatcher.chat_with_tools(
                        llm=self.llm,
                        messages=messages,
                        system_prompt=system_prompt,
                        max_tool_rounds=self.config.tool.max_tool_rounds,
                    )
            else:
                with console.status("[cyan]Thinking...[/cyan]", spinner="dots"):
                    response = await self.llm.chat(messages, system_prompt=system_prompt)

            self.conversation.add_message(LLMMessage(role="assistant", content=response.content))
            md = Markdown(response.content)
            name = self._get_active_personality().replace("_", " ").title()
            console.print(f"\n[bold cyan]{name}[/bold cyan]:")
            console.print(md)

            if response.usage:
                cost = response.usage.get("cost", 0)
                tokens = response.usage.get("total_tokens", 0)
                if cost or tokens:
                    console.print(f"[dim]Tokens: {tokens} | Cost: ${cost:.6f}[/dim]")

        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            self.conversation._messages.pop()

    async def cleanup(self) -> None:
        if self.llm:
            try:
                await self.llm.close()
            except Exception:
                pass
        self.conversation.close()
        self.memory_manager.close()
        if self.service_manager:
            try:
                await self.service_manager.close()
            except Exception:
                pass
        try:
            from core.tools.browser import PlaywrightManager
            pw = await PlaywrightManager.get_instance()
            if pw.available:
                await pw.close()
        except Exception:
            pass


async def main() -> None:
    from dotenv import load_dotenv
    load_dotenv()

    cli = JARVISCLI()
    await cli.run()


if __name__ == "__main__":
    asyncio.run(main())
