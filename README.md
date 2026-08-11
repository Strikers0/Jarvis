<img width="160" height="120" alt="1785344157634" src="https://github.com/user-attachments/assets/cbadd858-184a-4798-a27c-d1f1ea8dec0e" />
# JARVIS - Intelligent Personal AI Assistant

A terminal-based AI assistant with personality switching, conversation memory, **live voice conversations**, audio file processing via Sarvam API, desktop/browser automation via LLM function calling, **communication & productivity services** (email, calendar, notes, calls, weather & news), and **Telegram messaging** (chat with JARVIS from Telegram as a userbot).

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

### Live Voice Mode (Talk to JARVIS)

Have a live spoken conversation: **microphone → Sarvam STT → LLM (with tool use) → Sarvam TTS → speaker**.

```powershell
.\venv\Scripts\python.exe main.py --voice
```

Requirements:
- `SARVAM_API_KEY` set in `.env` — used for both speech-to-text and text-to-speech
- A working microphone (auto-detected on startup)

On launch you'll see which microphone was selected:

```
Loaded 25 tools
Using microphone: Headset (Airdopes 219 Hands-Free AG Audio)
Voice mode active. Speak... (Ctrl+C to stop)
Listening...
```

#### Choosing a Voice for Each Personality

Each personality has its own TTS voice from the [Sarvam AI Bulbul v3 voice catalog](https://docs.sarvam.ai/api/api-guides-tutorials/text-to-speech/voices) (35+ voices). Male personalities default to male voices (e.g. `shubh`, `aditya`) and female personalities to female voices (e.g. `ishita`, `neha`).

Pick a voice interactively from the text CLI:

```
/voice jarvis        # choose a voice for the jarvis personality
/voice               # choose a voice for the active personality
```

You'll be shown a numbered list of voices matching the personality's gender. Enter a number (or a voice name) to select it, or press Enter to keep the current one. The choice is saved to `runtime/personality_voices.json` (gitignored) and used the next time you run live voice mode or audio file mode.

You can also set `sarvam_voice` on a custom personality in a YAML file:
```yaml
- name: my_friend
  gender: female
  system_prompt: "..."
  sarvam_voice: priya
```

**How it works:**

1. JARVIS listens continuously. Speak, then pause for ~1 second — it stops recording on silence.
2. Speech is transcribed by Sarvam STT.
3. The text is sent to the LLM **with all tools enabled**, so you can command it by voice:
   - "Open Chrome and search for Python tutorials"
   - "Play lofi music on YouTube"
   - "Search the web for the weather today"
   - "Take a screenshot"
4. The reply is spoken aloud via Sarvam TTS, then JARVIS listens again.

**Notes:**
- Press **Ctrl+C** to stop voice mode.
- The spoken reply is also saved to `runtime/response.wav`.
- **Microphone selection:** the loudest working input device is chosen automatically. To force a specific mic, set the device name (or index) via the `JARVIS_MIC_DEVICE` environment variable:

  ```powershell
  $env:JARVIS_MIC_DEVICE = "Airdopes"   # any substring of the device name
  python main.py --voice
  ```

  Run `python -c "import sounddevice; print(sounddevice.query_devices())"` to list device names and indices.
- The speech/noise threshold auto-calibrates on every listen, so it adapts to your microphone and room noise.

### Telegram Mode (Chat with JARVIS on Telegram)

Chat with JARVIS from Telegram using an MTProto userbot (Telethon — not the Bot API).
Each Telegram chat gets its own conversation session and memory.

```powershell
.\venv\Scripts\python.exe main.py --telegram
```

Requirements:
- `TELEGRAM_ENABLED=true` and `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` set in `.env`
  (get them at https://my.telegram.org). First run prompts for your phone number
  and login code; the session is persisted locally.
- `TELEGRAM_ALLOWED_USERS` — comma-separated Telegram user ids allowed to talk to
  JARVIS (deny-by-default: unlisted users get "not authorized").
- `TELEGRAM_OWNER_CHAT_ID` — chat used for proactive reminders.
- Optional `SARVAM_API_KEY` enables voice-note replies (STT in / TTS out).

What works:
- Plain text chat with full tool use (confirmations happen inline in the chat).
- **Saved Messages console**: message yourself in Telegram's "Saved Messages"
  to issue commands; JARVIS reads them and replies back in the same chat.
  Outgoing messages you send from any device are treated as commands; JARVIS's
  own replies are ignored to avoid echo loops.
- Slash commands: `/help`, `/personality`, `/voice`, `/services`, `/notes`,
  `/todos`, `/remind`, `/model`, `/memory`, `/clear`.
- Voice notes: decoded to 16 kHz WAV → Sarvam STT → chat → Sarvam TTS (personality
  voice) → voice-note reply.
- Proactive reminders pushed to the owner chat.

#### Telegram Security Model

- **Deny-by-default**: only users listed in `TELEGRAM_ALLOWED_USERS` can talk to
  JARVIS. Everyone else is **silently ignored** (no reply at all, so strangers
  aren't bothered and JARVIS stays hidden).
- **Inline confirmations**: write/send/delete operations prompt "Allow this action?
  Reply yes or no." in the chat before executing. Reads (weather, notes, news,
  history) run automatically. Confirmations time out after 120s if unanswered.
- **Per-chat isolation**: each Telegram chat has its own conversation session and
  memory scope (`user_id`), so different users never see each other's context.

Telegram is implemented as **just another messaging service** behind the
platform-neutral `MessagingService` interface, so future platforms (WhatsApp,
Discord, Slack, Signal, SMS) plug in with the same contract.

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
| `/services` | Show communication/producitivity service health |
| `/notes` | List saved notes |
| `/todos` | List to-do items |
| `/remind` | List upcoming reminders |
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
- `EMAIL_USERNAME`, `EMAIL_PASSWORD`, `EMAIL_IMAP_HOST`, `EMAIL_SMTP_HOST`, `EMAIL_FROM`
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`, `GOOGLE_CALENDAR_ID`
- `WEATHER_API_KEY`, `NEWS_API_KEY`
- `TELEGRAM_ENABLED`, `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_SESSION_NAME`,
  `TELEGRAM_ALLOWED_USERS`, `TELEGRAM_OWNER_CHAT_ID`, `TELEGRAM_VOICE_ENABLED`

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

### Available Tools (54 total)

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

**Browser (5)**
| Tool | Description |
|---|---|
| `search_web` | General web search, return top results |
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

## Communication & Productivity Services (Phase 4)

JARVIS can send/read email, manage calendar events and reminders, take notes and to-dos, look up weather/news/stocks, and place calls. Everything is registered as LLM tools, so you can just ask in natural language.

### Available Service Tools

| Service | Tools |
|---|---|
| **Email** (`send_email`, `read_unread_emails`, `search_emails`) | IMAP/SMTP. For Gmail use an **App Password**. Configure via env: `EMAIL_IMAP_HOST`, `EMAIL_SMTP_HOST`, `EMAIL_USERNAME`, `EMAIL_PASSWORD`, `EMAIL_FROM` |
| **Calendar** (`create_event`, `list_events`, `search_events`, `delete_event`, `create_reminder`, `list_reminders`, `delete_reminder`) | Local SQLite by default; optional Google Calendar sync via OAuth2 (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`, `GOOGLE_CALENDAR_ID`). Natural-language times: "tomorrow at 10am", "in 2 hours", "next friday at 3pm" |
| **Notes & To-Do** (`create_note`, `list_notes`, `search_notes`, `delete_note`, `create_todo`, `list_todos`, `mark_todo`, `delete_todo`) | Local SQLite (`notes.db`) |
| **External APIs** (`get_weather`, `get_news`, `get_stock`, `get_crypto`, `get_wikipedia`) | Weather via OpenWeatherMap or wttr.in fallback (no key needed); news via NewsAPI or Google News RSS fallback; stocks via Yahoo Finance; crypto via CoinGecko; Wikipedia summaries |
| **Phone calls** (`make_call`, `save_contact`, `list_contacts`, `call_logs`) | Twilio VoIP when configured (`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`, `provider: twilio`); local contacts + call log otherwise |
| **Telegram** (`send_message`, `send_file`, `send_voice`) | MTProto userbot via Telethon. Launch with `python main.py --telegram`. Requires `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and `TELEGRAM_ALLOWED_USERS` (deny-by-default allow-list) |

### Example Queries

> "Send an email to john@example.com titled Project Update saying the deployment is done"
> "What unread emails do I have?"
> "Add a calendar event for tomorrow at 10am called Team Standup"
> "Remind me in 2 hours to take a break"
> "Create a note called Shopping with items milk and eggs"
> "Add buy groceries to my to-dos"
> "What's the weather in Delhi?"
> "Get the latest news about AI"
> "Call Mom"

### Service Health

Use `/services` in the CLI to see which services are configured and reachable. Unconfigured services (e.g. email without keys) return an error status but never crash the assistant. The `/services` command also works from Telegram (`/services` in a chat).

---

## Live Voice Mode

See the [Live Voice Mode](#live-voice-mode-talk-to-jarvis) usage section above. The voice stack lives in `voice/`:

```
Microphone (auto-detected) → callback recorder → VAD (silence detection)
    → Sarvam STT → LLM (with tools) → Sarvam TTS → speaker (non-blocking playback)
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
│   ├── session.py     # JarvisSession — shared runtime (LLM + conv + tools + services)
│   ├── memory/        # Long-term & vector memory
│   ├── tools/         # Tool calling framework
│   │   ├── base.py    # Tool ABC, ToolRegistry, ToolDispatcher, PermissionManager
│   │   ├── desktop.py # Desktop automation (PowerShell/user32 helpers in win.py)
│   │   ├── browser.py # Browser automation (Playwright + HTTP fallback)
│   │   ├── media.py   # Media control tools
│   │   ├── system.py  # File & system tools
│   │   └── win.py     # PowerShell desktop helpers (keys, mouse, clipboard)
│   ├── services/      # Phase 4: communication & productivity
│   │   ├── base.py    # Service ABC + service_tool() tool factory
│   │   ├── messaging.py    # MessagingService ABC + platform-neutral models
│   │   ├── telegram.py     # TelegramService (lifecycle, sends, allow-list)
│   │   ├── telegram_client.py  # Telethon singleton (only Telethon-touching file)
│   │   ├── telegram_events.py   # Inbound event handler + slash commands
│   │   ├── telegram_models.py   # TelegramRecipient / TelegramInboundMessage
│   │   ├── telegram_voice.py    # Voice-note STT → chat → TTS processor
│   │   ├── telegram_confirmation.py # Inline yes/no confirmations for tools
│   │   ├── telegram_reminders.py    # Background due-reminder poller
│   │   ├── telegram_runner.py       # run_telegram() wiring (main.py --telegram)
│   │   ├── notes.py   # Notes & to-dos (SQLite)
│   │   ├── email.py   # IMAP/SMTP send & read
│   │   ├── calendar.py# Events, reminders, Google Calendar OAuth2
│   │   ├── external.py# Weather, news, stocks, crypto, Wikipedia
│   │   ├── calling.py # Twilio calls + contacts + call log
│   │   └── __init__.py# ServiceManager orchestration
│   └── agent/         # Agent orchestration
│       └── graph.py   # AgentGraph (analyze → select → execute → synthesize)
├── tests/             # Unit tests (pytest)
├── voice/             # Voice pipeline
│   ├── sarvam_stt.py  # Sarvam STT API wrapper
│   ├── sarvam_tts.py  # Sarvam TTS API wrapper
│   ├── pipeline.py    # STT → LLM → TTS pipeline
│   ├── audio.py       # Decode any audio → 16kHz mono WAV (PyAV)
│   ├── microphone.py  # Mic auto-detection + callback recorder + VAD
│   ├── player.py      # Non-blocking WAV playback
│   ├── controller.py  # VoiceController (live listen → STT → LLM → TTS loop)
│   └── logger.py      # Voice logging
├── cli/
│   ├── main.py        # Chat CLI interface
│   ├── voice_main.py  # Audio file processor
│   └── voice_live.py  # Live voice mode entry (main.py --voice)
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
| Voice mode picks a mic that hears nothing | Force a working mic: `$env:JARVIS_MIC_DEVICE = "<device name>"` then `python main.py --voice` |
| Voice mode never hears me / threshold too high | Speak closer to the mic, or in a quiet room; the threshold auto-calibrates each listen |
| No audio plays back | Check speakers/volume; response is saved to `runtime/response.wav` |
| Personality not found | Names are case-insensitive; use `/personality` to list |
| `--telegram`: "Telegram service is not enabled" | Set `services.telegram.enabled=true` in `config.yaml` or `TELEGRAM_ENABLED=true` in `.env` |
| `--telegram`: "Telethon is not installed" | Install it: `pip install telethon` |
| Telegram messages get no reply | Only users in `TELEGRAM_ALLOWED_USERS` get a reply; others are silently ignored. Add your user id (comma-separated) to allow more people |
| Telegram voice notes reply "not supported" | Set `SARVAM_API_KEY` in `.env` to enable STT/TTS |
