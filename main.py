from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path


def main() -> None:
    from dotenv import load_dotenv
    load_dotenv()

    audio_path = None
    if "--audio" in sys.argv:
        idx = sys.argv.index("--audio")
        if idx + 1 < len(sys.argv) and not sys.argv[idx + 1].startswith("--"):
            audio_path = sys.argv[idx + 1]

    if audio_path is not None or "--audio" in sys.argv:
        if not audio_path:
            from rich.console import Console
            console = Console()
            while not audio_path:
                audio_path = console.input("[cyan]Enter audio file path (or 'exit' to quit):\n> [/cyan]").strip()
                if audio_path.lower() in ("exit", "quit", ""):
                    sys.exit(0)
                audio_path = audio_path.strip("\"'")
                if not os.path.isfile(audio_path):
                    console.print(f"[red]File not found:[/red] {audio_path}")
                    audio_dir = Path.cwd()
                    audio_files = list(audio_dir.glob("*.mp3")) + list(audio_dir.glob("*.wav")) + list(audio_dir.glob("*.m4a"))
                    if audio_files:
                        console.print("[yellow]Available audio files in current directory:[/yellow]")
                        for f in audio_files[:10]:
                            console.print(f"  {f.name}")
                    audio_path = None
        from cli.voice_main import process_audio_file
        asyncio.run(process_audio_file(audio_path))
        return

    from cli.main import JARVISCLI
    cli = JARVISCLI()
    asyncio.run(cli.run())


if __name__ == "__main__":
    main()
