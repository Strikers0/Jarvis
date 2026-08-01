# JARVIS — Live Voice Workflow Pipeline

This document describes how live voice mode (`python main.py --voice`) works, end to end.

## High-Level Flow

```
You (speak)
   │
   ▼
┌───────────────────┐
│  LISTEN (mic)     │   voice/microphone.py
└─────────┬─────────┘
          │ 16kHz mono float32 WAV bytes
          ▼
┌───────────────────┐
│  STT (Sarvam)     │   voice/sarvam_stt.py
└─────────┬─────────┘
          │ transcript text
          ▼
┌───────────────────┐
│  THINK (LLM)      │   core/llm.py + core/tools (ToolDispatcher)
│  + TOOL USE       │   max 5 tool rounds (open apps, web search, media…)
└─────────┬─────────┘
          │ reply text
          ▼
┌───────────────────┐
│  SPEAK (Sarvam)   │   voice/sarvam_tts.py → runtime/response.wav
└─────────┬─────────┘   voice/player.py (non-blocking playback)
          │
          ▼
   back to LISTEN (loop until Ctrl+C)
```

---

## 1. Startup (one-time)

Entry point: `cli/voice_live.py` → `voice_live()`

| Step | Responsibility | Code |
|---|---|---|
| Load config | `config.yaml` + `.env` (API keys) | `core/config.py` |
| Personality | Set active personality from config | `core/personality.py` |
| Conversation + memory | New session; memories injected later | `core/conversation.py`, `core/memory/` |
| LLM | Build provider (OpenRouter/OpenAI/Gemini) | `core/llm.py` |
| Tools | Register 25 tools across 4 tool sets → PermissionManager → ToolDispatcher | `core/tools/` |
| Sarvam | Build STT (`saaras:v3`) and TTS (`bulbul:v3`) wrappers | `voice/sarvam_stt.py`, `voice/sarvam_tts.py` |
| Mic | `resolve_mic()` scans inputs, measures 0.5 s RMS each, picks loudest live device (or `JARVIS_MIC_DEVICE` override) | `voice/microphone.py` |

Console output on success:

```
Loaded 25 tools
Using microphone: Headset (Airdopes 219 Hands-Free AG Audio)
Voice mode active. Speak... (Ctrl+C to stop)
```

---

## 2. The Turn Loop

`voice/controller.py` → `VoiceController.run()` → `_turn()` (repeats forever)

### 2.1 LISTEN — `record_until_silence(device)`

`voice/microphone.py`

1. `MicrophoneRecorder` opens a callback-based `sounddevice.InputStream`
   (16 kHz, mono, float32, 100 ms blocks) — non-blocking, async-safe.
2. Each block's RMS is computed.
3. Auto-calibrated noise threshold: `max(0.015, median(noise_floor) × 5)`.
4. Voice is detected when RMS crosses the threshold; recording continues until
   1.0 s of silence (hard caps: 20 s max speech, 15 s listen timeout).
5. Returns raw float32 samples, or `None` if no speech.

### 2.2 STT — `SarvamSTT.transcribe(wav_bytes)`

`voice/sarvam_stt.py`

- Samples → in-memory WAV (`samples_to_wav_bytes()`).
- Sent to Sarvam STT API → transcript.
- Printed as `You: <transcript>` and appended to conversation history.

### 2.3 THINK — LLM with tool use

`core/llm.py`, `core/tools/base.py`

- System prompt = active personality + memory facts + tool guidance.
- `ToolDispatcher.chat_with_tools(..., max_tool_rounds=5)` lets the LLM call tools:
  `open_app`, `search_web`, `search_google`, `search_youtube`, `open_url`,
  `play_music`, `play_youtube`, `screenshot`, `execute_command`, etc.
- Final reply is printed as `Jarvis: <reply>` and appended to history.

### 2.4 SPEAK — `SarvamTTS.synthesize(reply)`

`voice/sarvam_tts.py`, `voice/player.py`

- Reply synthesized to `runtime/response.wav`.
- `player.play_wav_start()` plays it on the speakers **without blocking** the loop.
- Waits until playback finishes, then returns to LISTEN.

---

## 3. Teardown

`voice/controller.py` → `cleanup()` (on Ctrl+C)

```
stop_playback() → close STT → close TTS → close LLM → close conversation → close memory
```

---

## Key Properties

- **Non-blocking audio everywhere** — no Ctrl+C hangs (previously caused by blocking audio calls in threads).
- **Adaptive VAD** — threshold recalibrates each turn from the live noise floor.
- **Mic auto-detection** — picks the loudest *working* input, not the OS default (which can be dead).
- **Force a mic** — `$env:JARVIS_MIC_DEVICE = "Airdopes"` (substring of device name) before running.
- **Tools in voice mode** — confirmations are auto-approved (`confirm_callback=lambda: True`).
- **Memory-aware** — facts are injected into the system prompt every turn.

## Relevant Files

| File | Purpose |
|---|---|
| `cli/voice_live.py` | Entry point, builds everything, wires `--voice` |
| `voice/controller.py` | Turn loop and teardown |
| `voice/microphone.py` | Mic detection, callback recorder, VAD, WAV encoding |
| `voice/sarvam_stt.py` | Speech-to-text wrapper |
| `voice/sarvam_tts.py` | Text-to-speech wrapper |
| `voice/player.py` | Non-blocking WAV playback |
| `core/tools/` | Tool registry, dispatcher, permission manager + 25 tools |
| `main.py` | CLI flag routing (`--voice` → `voice_live`) |
