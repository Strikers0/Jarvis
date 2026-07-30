# Project JARVIS - Phase-wise Implementation Plan

Based on: Problem Statement - Project JARVIS: Intelligent Personal AI Assistant

---

## Phase 1: Core Conversational Engine (Weeks 1-4)

### Objective
Build a terminal-based conversational AI with LLM integration, conversation history, and personality switching.

### Deliverables
- [ ] Terminal-based chat interface
- [ ] LLM integration via OpenRouter/OpenAI/Gemini
- [ ] Conversation history management (in-memory + persistence)
- [ ] Personality system with 10+ personalities
- [ ] Configuration management (API keys, settings)

### Technical Tasks

#### 1.1 Project Setup & Infrastructure
- [ ] Initialize Python project with `pyproject.toml` (poetry/uv)
- [ ] Set up project structure:
  ```
  jarvis/
  ├── core/
  │   ├── config.py          # Configuration management
  │   ├── llm.py             # LLM abstraction layer
  │   ├── conversation.py    # Conversation history management
  │   └── personality.py     # Personality system
  ├── cli/
  │   └── main.py            # CLI entry point
  ├── personalities/         # Personality definitions
  │   ├── base.py
  │   ├── male/
  │   └── female/
  ├── config.yaml            # User configuration
  └── main.py                # Entry point
  ```
- [ ] Set up logging, error handling, config validation
- [ ] Create `.env.example` for API keys

#### 1.2 LLM Abstraction Layer (`core/llm.py`)
- [ ] Abstract base class `LLMProvider`
- [ ] Implement providers:
  - [ ] `OpenRouterProvider` (primary - supports multiple models)
  - [ ] `OpenAIProvider` (fallback)
  - [ ] `GeminiProvider` (fallback)
  - [ ] `LocalLLMProvider` (Ollama/Llama.cpp - future)
- [ ] Unified interface: `chat(messages, personality, tools)`
- [ ] Streaming response support
- [ ] Token counting & cost tracking
- [ ] Retry logic with exponential backoff
- [ ] Model configuration per personality

#### 1.3 Conversation Management (`core/conversation.py`)
- [ ] `ConversationManager` class
- [ ] In-memory message history with configurable window
- [ ] Persistence to SQLite (`conversations.db`)
- [ ] Session management (create, load, list, delete sessions)
- [ ] Context window management (token-aware truncation)
- [ ] Export/import conversation history (JSON)

#### 1.4 Personality System (`core/personality.py`)
- [ ] `Personality` base class with:
  - `name`, `gender`, `description`
  - `system_prompt` template
  - `voice_id` (for TTS later)
  - `traits`: tone, vocabulary, humor_style, formality
- [ ] `PersonalityManager` for loading/switching personalities
- [ ] Pre-defined personalities (10 total):
  - **Male**: JARVIS, Friendly Buddy, Teacher, Motivator, Funny
  - **Female**: Professional Assistant, Caring Friend, Tutor, Motivator, Cheerful Companion
- [ ] Personality switching mid-conversation with context preservation
- [ ] Custom personality creation via YAML config

#### 1.5 Configuration (`core/config.py`)
- [ ] Pydantic-based config models
- [ ] `config.yaml` with:
  - LLM provider & model settings
  - Active personality
  - Conversation settings (history length, temperature)
  - TTS/STT settings (for Phase 2)
  - Tool permissions
- [ ] Environment variable overrides
- [ ] Config validation on startup

#### 1.6 CLI Interface (`cli/main.py`)
- [ ] Rich/Textual-based TUI
- [ ] Commands: `/personality`, `/history`, `/clear`, `/save`, `/load`, `/model`, `/help`
- [ ] Streaming response display with typing effect
- [ ] Multi-line input support
- [ ] Personality preview before switching

### Milestone
- [ ] Working terminal chatbot with personality switching
- [ ] Conversation persists across sessions
- [ ] All 10 personalities functional
- [ ] Configurable LLM providers

---

## Phase 2: Voice Interface & Memory System (Weeks 5-8)

### Objective
Add voice interaction (STT/TTS) and persistent long-term memory.

### Deliverables
- [ ] Voice input (Speech-to-Text)
- [ ] Voice output (Text-to-Speech)
- [ ] Wake word detection (optional, Phase 2B)
- [ ] Long-term memory system (SQLite + Vector DB)
- [ ] Memory recall in conversations

### Technical Tasks

#### 2.1 Speech-to-Text (`core/stt.py`)
- [ ] Integrate `faster-whisper` (CTranslate2 backend)
- [ ] Model options: `tiny`, `base`, `small`, `medium`, `large-v3`
- [ ] VAD (Voice Activity Detection) for continuous listening
- [ ] Language detection (auto-detect en/hi)
- [ ] Streaming transcription for real-time feel
- [ ] Microphone input with noise suppression
- [ ] Configurable: model size, device (CPU/GPU), language

#### 2.2 Text-to-Speech (`core/tts.py`)
- [ ] Integrate `piper-tts` (offline, fast, multi-voice)
- [ ] Voice mapping per personality:
  - JARVIS → `en_US-lessac-medium` (or similar British male)
  - Friendly Buddy → `en_US-amy-low`
  - Hindi voices via Piper/Coqui
- [ ] Streaming TTS playback (low latency)
- [ ] SSML support for emphasis, pauses
- [ ] Voice cloning via Coqui/XTTS (Phase 2B)
- [ ] Interruptible playback (stop on user speech)

#### 2.3 Voice Pipeline (`core/voice.py`)
- [ ] `VoiceAssistant` orchestrator
- [ ] Pipeline: Mic → VAD → STT → LLM → TTS → Speaker
- [ ] Turn-taking logic (VAD-based interruption)
- [ ] Wake word detection (Porcupine/Picovoice - Phase 2B)
- [ ] Audio device selection & configuration

#### 2.4 Memory System (`core/memory/`)
- [ ] **Short-term**: Conversation history (Phase 1)
- [ ] **Long-term** (`core/memory/long_term.py`):
  - SQLite for structured facts (user profile, preferences, facts)
  - ChromaDB/Qdrant for semantic memory (embeddings)
  - Schema:
    ```sql
    CREATE TABLE facts (
      id, user_id, category, key, value, confidence, created_at, updated_at
    );
    CREATE TABLE preferences (
      id, user_id, key, value, updated_at
    );
    CREATE TABLE entities (
      id, user_id, name, type, attributes_json, updated_at
    );
    ```
- [ ] `MemoryManager` class:
  - `store_fact(category, key, value, confidence)`
  - `recall_fact(category, key)`
  - `search_semantic(query, top_k)`
  - `extract_entities(text)` → LLM-based extraction
- [ ] Memory injection into LLM context (relevant facts only)
- [ ] Periodic memory consolidation (summarize old conversations)

#### 2.5 Memory-Aware Conversation Manager
- [ ] Extend `ConversationManager` with memory injection
- [ ] Pre-prompt injection: relevant facts + recent summary
- [ ] Automatic fact extraction from conversations (background task)
- [ ] User confirmation for sensitive facts

#### 2.6 Voice CLI Integration (`cli/voice_main.py`)
- [ ] Voice mode toggle: `--voice` flag
- [ ] Visual audio level indicator
- [ ] Transcription display in real-time
- [ ] Keyboard interrupt handling (Ctrl+C to stop speaking)

### Milestone
- [ ] Full voice conversation working (STT → LLM → TTS)
- [ ] 10+ personalities with distinct voices
- [ ] Long-term memory persists across sessions
- [ ] Assistant recalls facts in future conversations
- [ ] Hindi/Hinglish STT/TTS functional

---

## Phase 3: Desktop Automation & Tool Use (Weeks 9-14)

### Objective
Enable the assistant to perform desktop tasks, browser automation, and tool use via LLM function calling.

### Deliverables
- [ ] Tool calling framework (LangGraph-based)
- [ ] Desktop automation (PyAutoGUI)
- [ ] Browser automation (Playwright)
- [ ] Application launcher
- [ ] Google/YouTube search
- [ ] Media control
- [ ] File operations

### Technical Tasks

#### 3.1 Tool Calling Framework (`core/tools/`)
- [ ] `Tool` base class with JSON schema
- [ ] `ToolRegistry` for registration/discovery
- [ ] `ToolDispatcher` with LLM function calling
- [ ] Permission system (allow/deny per tool)
- [ ] Execution sandboxing (subprocess isolation for risky tools)
- [ ] Tool result formatting for LLM context

#### 3.2 Desktop Automation Tools (`core/tools/desktop.py`)
- [ ] `open_app(app_name)` - Launch applications
- [ ] `close_app(app_name)` - Close applications
- [ ] `type_text(text)` - Simulate typing
- [ ] `press_key(key)` - Key presses (Enter, Tab, etc.)
- [ ] `click(x, y)` / `click_element(selector)` - Mouse control
- [ ] `screenshot()` - Capture screen
- [ ] `get_volume()` / `set_volume(level)` - System volume
- [ ] `get_clipboard()` / `set_clipboard(text)`
- [ ] Window management: minimize, maximize, focus
- [ ] App discovery: scan Start Menu, PATH for executables

#### 3.3 Browser Automation Tools (`core/tools/browser.py`)
- [ ] Playwright integration (Chromium/Firefox)
- [ ] `search_google(query)` - Open Google, search, return top results
- [ ] `search_youtube(query)` - Search and play first result
- [ ] `open_url(url)` - Navigate to URL
- [ ] `click_selector(selector)` - Click elements
- [ ] `extract_text(selector)` - Scrape content
- [ ] `fill_form(selector, value)` - Form filling
- [ ] Session persistence (cookies, login state)
- [ ] Headless/headful mode toggle

#### 3.4 Media & System Tools (`core/tools/media.py`, `core/tools/system.py`)
- [ ] `play_music(query)` - YouTube Music/Spotify Web
- [ ] `play_youtube_video(query)`
- [ ] `control_media(action)` - play/pause/next/prev
- [ ] `take_screenshot(save_path)`
- [ ] `open_file(path)` - Open with default app
- [ ] `create_folder(path)` / `list_directory(path)`
- [ ] `search_files(query, path)` - Everything/Windows Search API

#### 3.5 Tool Orchestration with LangGraph (`core/agent/`)
- [ ] Define `AgentState` with: messages, tools, memory, context
- [ ] Build `AgentGraph` with nodes:
  - `analyze_intent` → `select_tools` → `execute_tools` → `synthesize_response`
- [ ] Support parallel tool execution
- [ ] Tool result validation & retry logic
- [ ] Human-in-the-loop for destructive actions (confirm before delete)

#### 3.6 LLM Tool Integration
- [ ] Convert tools to OpenAI function calling format
- [ ] Personality-aware tool selection (e.g., JARVIS uses precise commands)
- [ ] Multi-step task decomposition (planning node in graph)
- [ ] Tool execution streaming updates to user

#### 3.7 Safety & Permissions
- [ ] Permission levels: `auto`, `confirm`, `deny`
- [ ] Per-tool permission config
- [ ] Dangerous operation detection (delete, install, system changes)
- [ ] Audit log of all tool executions

### Milestone
- [ ] Assistant opens apps, searches web, plays music via voice
- [ ] Multi-step tasks: "Open Chrome and search for Python tutorials"
- [ ] Browser automation works for common sites
- [ ] Safe tool execution with confirmations

---

## Phase 4: Communication & Productivity (Weeks 15-20)

### Objective
Integrate messaging, email, calendar, notes, and productivity features.

### Deliverables
- [ ] WhatsApp integration (send/read/reply)
- [ ] Phone calls (VoIP/mobile)
- [ ] Email (send/read)
- [ ] Calendar management
- [ ] Notes & reminders
- [ ] Weather & news

### Technical Tasks

#### 4.1 WhatsApp Integration (`core/services/whatsapp.py`)
- [ ] **Option A**: WhatsApp Web automation (Playwright)
  - QR code login persistence
  - Contact search
  - Send text/image/voice
  - Read unread messages
  - Listen for incoming (polling/webhook)
- [ ] **Option B**: WhatsApp Business API (official, paid)
- [ ] **Option C**: `whatsapp-web.js` via Node.js bridge
- [ ] Contact resolution: "Message mom" → find contact
- [ ] Privacy: local-only, no cloud sync

#### 4.2 Phone Calling (`core/services/calling.py`)
- [ ] VoIP via Twilio/Plivo/SIP
- [ ] Android integration (Phase 5) for native calls
- [ ] Contact lookup from memory
- [ ] Call logging

#### 4.3 Email (`core/services/email.py`)
- [ ] IMAP/SMTP integration
- [ ] Gmail/Outlook OAuth2
- [ ] `send_email(to, subject, body, attachments)`
- [ ] `read_unread(count)` - summarize unread
- [ ] `search_emails(query)`

#### 4.4 Calendar & Reminders (`core/services/calendar.py`)
- [ ] Google Calendar API / CalDAV
- [ ] `create_event(title, datetime, duration, attendees)`
- [ ] `list_events(date_range)`
- [ ] Reminders: persistent notifications (plyer/win10toast)
- [ ] Natural language parsing: "Remind me tomorrow at 10am"

#### 4.5 Notes & To-Do (`core/services/notes.py`)
- [ ] Local SQLite storage (Markdown support)
- [ ] `create_note(title, content, tags)`
- [ ] `search_notes(query)`
- [ ] `create_todo(task, due_date, priority)`
- [ ] `list_todos(filter)`
- [ ] Sync with Obsidian/Notion (optional)

#### 4.6 External APIs (`core/services/external.py`)
- [ ] Weather: OpenWeatherMap / WeatherAPI
- [ ] News: NewsAPI / RSS feeds
- [ ] Stock/crypto prices
- [ ] Wikipedia/WolframAlpha for facts

#### 4.7 Service Orchestration
- [ ] Unified `ServiceManager` for all integrations
- [ ] OAuth2 token management (refresh, storage)
- [ ] Service health checks
- [ ] Unified tool interface for LLM

### Milestone
- [ ] "Message mom on WhatsApp" works end-to-end
- [ ] Calendar events created via voice
- [ ] Email composition via dictation
- [ ] Daily briefing: weather, news, calendar

---

## Phase 5: Mobile App & Advanced Features (Weeks 21-28)

### Objective
Android app, cross-device sync, long-term memory, autonomous agents.

### Deliverables
- [ ] Flutter Android app
- [ ] Cross-device synchronization
- [ ] Vector database for semantic memory
- [ ] Autonomous multi-step agents
- [ ] Plugin/extension system

### Technical Tasks

#### 5.1 Android App (`mobile/flutter_app/`)
- [ ] Flutter project setup
- [ ] Voice UI: wake word → STT → streaming → TTS
- [ ] Local STT/TTS (TensorFlow Lite / Piper)
- [ ] Chat history sync (WebSocket/REST to desktop)
- [ ] Settings: personality, voice, permissions
- [ ] Notification listener for WhatsApp/SMS
- [ ] Android Auto integration (future)
- [ ] Offline mode (local LLM via llama.cpp)

#### 5.2 Cross-Device Sync (`core/sync/`)
- [ ] WebSocket server (desktop) ↔ Client (mobile)
- [ ] Sync: conversations, memory, settings, personality
- [ ] Conflict resolution (last-write-wins + manual merge)
- [ ] E2E encryption for sync data
- [ ] QR code pairing

#### 5.3 Advanced Memory (`core/memory/vector.py`)
- [ ] Migrate to Qdrant/Weaviate (local or cloud)
- [ ] Embedding model: `sentence-transformers/all-MiniLM-L6-v2` or `BAAI/bge-small`
- [ ] Memory types:
  - Episodic (conversations)
  - Semantic (facts, knowledge)
  - Procedural (learned procedures)
- [ ] Memory consolidation pipeline (background job)
- [ ] Forgetting curve / relevance decay

#### 5.4 Autonomous Agent (`core/agent/autonomous.py`)
- [ ] LangGraph-based planner
- [ ] Goal decomposition: "Plan my trip to Goa" → subtasks
- [ ] Tool chaining with verification
- [ ] Self-correction on tool failure
- [ ] Human checkpoints for irreversible actions
- [ ] Background task execution (cron-like)

#### 5.5 Plugin System (`core/plugins/`)
- [ ] Plugin specification (manifest.yaml, entrypoint)
- [ ] Sandbox execution (subprocess with restrictions)
- [ ] Plugin marketplace (local directory + GitHub)
- [ ] Example plugins:
  - Home Assistant / IoT control
  - Spotify control
  - Code execution (Jupyter kernel)
  - Translation

#### 5.6 Personality Voice Cloning (Advanced)
- [ ] XTTS-v2 / OpenVoice integration
- [ ] User voice cloning (consent-based)
- [ ] Personality-specific voice profiles

#### 5.7 Desktop UI (`desktop/tauri_app/`)
- [ ] Tauri + React/Svelte frontend
- [ ] System tray app with always-on-top chat
- [ ] Voice visualization
- [ ] Settings dashboard
- [ ] Plugin manager UI
- [ ] Conversation history browser

### Milestone
- [ ] Android app connects to desktop backend
- [ ] Seamless cross-device conversation
- [ ] Semantic memory recalls relevant context
- [ ] Autonomous multi-step tasks work reliably
- [ ] Plugin system allows extensions

---

## Cross-Cutting Concerns (All Phases)

### Testing Strategy
| Phase | Unit Tests | Integration Tests | E2E Tests |
|-------|------------|-------------------|-----------|
| 1     | LLM, Personality, Config | Conversation persistence | CLI chat session |
| 2     | STT, TTS, Memory | Voice pipeline | Voice conversation |
| 3     | Tools, Dispatcher | Tool execution | Multi-step desktop tasks |
| 4     | Services | API integrations | WhatsApp/Email flows |
| 5     | Sync, Plugins | Mobile ↔ Desktop | Full autonomous task |

- [ ] pytest + pytest-asyncio for async tests
- [ ] Mock LLM responses for deterministic tests
- [ ] Audio test fixtures for STT/TTS
- [ ] Playwright for browser tool tests

### Security
- [ ] API keys in system keyring (keyring library)
- [ ] Local-first: no data leaves machine without consent
- [ ] Tool permission system (Phase 3)
- [ ] Encrypted memory database (SQLCipher)
- [ ] Audit log for all tool executions

### Observability
- [ ] Structured logging (structlog)
- [ ] Metrics: latency, token usage, tool success rate
- [ ] Health check endpoint
- [ ] Debug mode with verbose LLM prompts

### Documentation
- [ ] Architecture decision records (ADRs)
- [ ] API documentation (docstrings + mkdocstrings)
- [ ] User guide (setup, configuration, personalities)
- [ ] Developer guide (adding tools, personalities, plugins)

---

## Phase Summary & Timeline

| Phase | Duration | Focus | Key Deliverable |
|-------|----------|-------|-----------------|
| 1 | 4 weeks | Core LLM Chat | Terminal JARVIS with personalities |
| 2 | 4 weeks | Voice + Memory | Voice JARVIS with long-term memory |
| 3 | 6 weeks | Desktop Automation | JARVIS controls PC & Browser |
| 4 | 6 weeks | Communication & Productivity | WhatsApp, Email, Calendar, Notes |
| 5 | 8 weeks | Mobile & Advanced | Android app, Sync, Autonomous agents |

**Total: ~28 weeks (7 months)**

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| LLM API costs | Local model fallback (Ollama), token budgets |
| STT/TTS latency | Streaming, smaller models, GPU acceleration |
| WhatsApp blocking | Multiple integration options, respect ToS |
| Cross-platform complexity | Phase 5 mobile optional; desktop-first |
| Memory bloat | Consolidation jobs, TTL, vector DB |
| Tool safety | Permission system, confirmations, sandboxing |

---

## Next Steps

1. **Initialize Phase 1**: Set up repo, config, LLM abstraction
2. **Define personality system prompts** for all 10 personalities
3. **Choose LLM provider defaults** (OpenRouter recommended)
4. **Set up CI/CD** with linting, type-checking, tests
5. **Create development environment** (devcontainer/venv)

---

*Document Version: 1.0*  
*Based on: Problem Statement - Project JARVIS*  
*Generated: 2025-07-25*