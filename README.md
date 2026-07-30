# JARVIS - Intelligent Personal AI Assistant

A terminal-based AI assistant with personality switching, conversation memory, audio file processing via Sarvam API, and desktop/browser automation via LLM function calling.

## Setup

### Prerequisites
- Python 3.11+
- An API key from one of: [OpenRouter](https://openrouter.ai/), [OpenAI](https://platform.openai.com/), or [Gemini](https://ai.google.dev/)
- A [Sarvam AI](https://www.sarvam.ai/) API key for audio file transcription and speech synthesis

### Quick Start

```powershell
# Create virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install JARVIS
pip install -e .

# Set up your API keys (use .env.example — NEVER create or commit a .env file)
copy .env.example .env
```

Edit `.env` (which is gitignored) and add your keys:
```
OPENROUTER_API_KEY=sk-or-...
SARVAM_API_KEY=your-sarvam-api-key
```

> **Security**: API keys are read exclusively from environment variables (via `.env` or system env). Never hardcode keys in `config.yaml` or source files. The `.env` file is in `.gitignore` and will never be committed.

---

## Usage

### Chat Mode (Text Only)

```powershell
.\venv\Scripts\Activate.ps1
python main.py
```

Type your message and press Enter to chat. Use `/help` to see all commands.

### Audio File Mode

Process an audio file through Sarvam STT → LLM → Sarvam TTS:

```powershell
# With a file path
.\venv\Scripts\python.exe main.py --audio "C:\path\to\input.mp3"

# Or without a path (prompts interactively)
.\venv\Scripts\python.exe main.py --audio
```

Supported formats: `.mp3`, `.wav`, `.m4a`.

Automatic conversion to 16 kHz mono PCM WAV is done internally. Output is saved to `runtime/response.wav`.

### In-Chat Commands

| Command | Description |
|---|---|
| `/personality` | List all personalities |
| `/personality <name>` | Switch personality |
| `/history` | Show conversation history |
| `/clear` | Clear conversation |
| `/sessions` | List saved sessions |
| `/save` | Export session to JSON |
| `/load <id>` | Load a session |
| `/model` | Show current model & token usage |
| `/memory` | Show stored memories |
| `/tools` | List available automation tools |
| `/audit` | Show tool execution audit log |
| `/help` | Show help |
| `/exit` | Exit |

### Personality Switching

JARVIS has 10 built-in personalities:

**Male**
| Name | Description |
|---|---|
| `jarvis` | Sophisticated AI assistant inspired by Tony Stark's JARVIS |
| `friendly_buddy` | Casual, warm, approachable friend |
| `teacher` | Patient, knowledgeable tutor |
| `motivator` | High-energy life coach |
| `funny` | Witty comedian companion |

**Female**
| Name | Description |
|---|---|
| `professional_assistant` | Polished, efficient executive assistant |
| `caring_friend` | Warm, empathetic companion |
| `tutor` | Encouraging mentor |
| `motivator_female` | Empowering coach |
| `cheerful_companion` | Bubbly, optimistic friend |

Switch mid-conversation:
```
/personality teacher
/personality caring_friend
```
Names are case-insensitive. Typing `/personality male` or `/personality female` lists all personalities of that gender.

### Security

### API Keys — Environment Variables Only
API keys must **never** be hardcoded in `config.yaml` or source code. They are read from environment variables in this order:
1. System/process environment variables (most secure)
2. `.env` file in the project root (gitignored — see `.env.example` for the template)

Supported environment variables:
- `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`
- `SARVAM_API_KEY`
- `LLM_PROVIDER`, `LLM_MODEL`
- `ACTIVE_PERSONALITY`

### Production Recommendation: Windows Credential Manager
For production use, store API keys in the **Windows Credential Manager** or a system keyring instead of a `.env` file. Use Python's `keyring` library to retrieve them at runtime.

### Database Encryption
The local SQLite databases (`conversations.db`, `memory.db`) store user conversation history and personal facts. For production deployment, consider:
- **SQLCipher** — encrypted SQLite via `pysqlcipher3`
- Encrypt the DB connection with a passphrase stored in the system keyring
- Or use a managed database with built-in encryption at rest

## Configuration

Edit `config.yaml` to change default settings. API keys must only be set via environment variables, not in this file.

```yaml
llm:
  provider: openrouter     # openrouter, openai, gemini
  model: openai/gpt-4o-mini
  temperature: 0.7

sarvam:
  stt_model: "saaras:v3"
  tts_model: "bulbul:v3"
  tts_speaker: meera
```

### Memory System

JARVIS automatically remembers facts about you (name, preferences, location, etc.) and uses them in conversations.

```
/memory       - View stored memories
/clear        - Clear conversation (memory persists)
```

### Audio File Pipeline (`--audio <file>`)

```
Audio File → PyAV decode → Resample (16kHz mono) → WAV in memory → Sarvam STT → LLM → Sarvam TTS → runtime/response.wav
```

1. **PyAV** — opens and decodes MP3/WAV/M4A files into PCM frames
2. **Resampler** — converts to 16kHz mono s16 PCM
3. **BytesIO → wave** — wraps PCM in WAV format in memory
4. **Sarvam STT** — transcribes WAV bytes to text via Sarvam API
5. **Conversation + LLM** — generates AI response
6. **Sarvam TTS** — synthesizes response to WAV audio file

---

## Desktop Automation & Tool Use

JARVIS can perform desktop tasks and browser automation via LLM-powered function calling. Every interaction is permission-controlled and audited.

### Available Tools (24 total)

**Desktop (11)**
| Tool | Description |
|---|---|
| `open_app` | Launch applications (notepad, chrome, spotify, etc.) |
| `close_app` | Close applications by process name |
| `type_text` | Simulate typing into the focused window |
| `press_key` | Press keyboard keys or combos (enter, ctrl+c, alt+tab) |
| `click` | Click at screen coordinates or current position |
| `screenshot` | Capture screen to file |
| `get_volume` / `set_volume` | Read or change system volume |
| `get_clipboard` / `set_clipboard` | Read or write system clipboard |
| `focus_window` | Bring a window to focus by title |

**Browser (4)**
| Tool | Description |
|---|---|
| `search_google` | Search Google, return top results |
| `search_youtube` | Search YouTube, return video links |
| `open_url` | Navigate to a URL |
| `extract_text` | Extract content from a webpage via CSS selector |

**Media (3)**
| Tool | Description |
|---|---|
| `play_youtube` | Open YouTube search or video |
| `play_music` | Search YouTube Music or Spotify |
| `control_media` | Play/pause/next/previous/stop |

**System (6)**
| Tool | Description |
|---|---|
| `open_file` | Open file/folder with default app |
| `create_folder` | Create directories |
| `list_directory` | List files in a directory |
| `search_files` | Recursively search for files |
| `get_system_info` | Show OS, CPU, memory, disk info |
| `execute_command` | Run a shell command (requires confirmation) |

### Example Queries

> "Open Chrome and search for Python tutorials"
> "What's the weather today?"
> "Take a screenshot"
> "Search YouTube for lofi music"
> "Create a folder called projects on my desktop"
> "List the files in my documents folder"

### Permissions

Configured in `config.yaml` under `tool.permissions`:

```yaml
tool:
  enabled: true
  max_tool_rounds: 5
  permissions:
    execute_command:
      level: confirm      # always ask before running shell commands
    close_app:
      level: confirm
    open_file:
      level: auto         # allow without asking
    search_google:
      level: auto
```

Three permission levels:
- **`auto`** — execute without asking
- **`confirm`** — prompt for approval each time (default)
- **`deny`** — block the tool entirely

Dangerous operations (delete, shutdown, install) are always flagged with ⚠.

### Browser Automation Setup

Playwright requires browser binaries to be installed (one-time):

```powershell
playwright install chromium
```

---

## Project Structure

```
jarvis/
├── core/              # Core engine
│   ├── config.py      # Configuration management
│   ├── llm.py         # LLM abstraction (OpenRouter, OpenAI, Gemini)
│   ├── conversation.py# Conversation history + memory-aware manager
│   ├── personality.py # Personality system
│   ├── memory/        # Long-term & vector memory
│   ├── tools/         # Tool calling framework
│   │   ├── base.py    # Tool ABC, ToolRegistry, ToolDispatcher, PermissionManager
│   │   ├── desktop.py # Desktop automation (PyAutoGUI)
│   │   ├── browser.py # Browser automation (Playwright)
│   │   ├── media.py   # Media control tools
│   │   └── system.py  # File & system tools
│   └── agent/         # Agent orchestration
│       └── graph.py   # AgentGraph (analyze → select → execute → synthesize)
├── voice/             # Sarvam API voice processing
│   ├── sarvam_stt.py  # Sarvam STT API wrapper
│   ├── sarvam_tts.py  # Sarvam TTS API wrapper
│   ├── pipeline.py    # STT → LLM → TTS pipeline
│   └── logger.py      # Voice logging
├── cli/
│   ├── main.py        # Chat CLI interface
│   └── voice_main.py  # Audio file processor
├── personalities/     # Personality definitions
├── config.yaml        # User settings
├── .env.example       # API key template (copy to .env)
├── .gitignore         # Git exclusion rules
├── pyproject.toml      # Project metadata & dependencies
├── README.md          # This file
└── main.py            # Entry point
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `No module named 'core'` | Run from `jarvis/` directory |
| `ModuleNotFoundError` | Activate venv: `.\venv\Scripts\Activate.ps1` |
| `Sarvam STT/TTS error` | Check `SARVAM_API_KEY` is set in `.env` or as an environment variable |
| `--audio`: "File not found" | Check the file path; use absolute path if needed |
| Personality not found | Names are case-insensitive; use `/personality` to list |
