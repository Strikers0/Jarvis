from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class LLMProviderConfig(BaseModel):
    provider: Literal["openrouter", "openai", "gemini"] = "openrouter"
    model: str = "openai/gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: int = 30
    retry_attempts: int = 3
    retry_delay: float = 2.0


class OpenRouterConfig(BaseModel):
    base_url: str = "https://openrouter.ai/api/v1"


class OpenAIConfig(BaseModel):
    base_url: str = "https://api.openai.com/v1"


class GeminiConfig(BaseModel):
    base_url: str = "https://generativelanguage.googleapis.com/v1beta"


class SarvamConfig(BaseModel):
    api_key: str = ""
    stt_model: str = "sarvam-1"
    tts_model: str = "sarvam-1"
    stt_language_code: str = "unknown"
    tts_language_code: str = "unknown"
    stt_with_translation: bool = True
    tts_speaker: str = "meera"
    tts_pitch: float = 0.0
    tts_pace: float = 1.0
    tts_loudness: float = 1.0
    tts_sample_rate: int = 22050


class VoiceConfig(BaseModel):
    provider: Literal["whisper", "sarvam"] = "whisper"
    stt_provider: Literal["whisper", "sarvam"] = "whisper"
    tts_provider: Literal["piper", "sarvam"] = "piper"
    silence_duration: float = 0.5  # seconds of quiet after speech before processing starts
    listen_timeout: float = 15.0


class PersonalityConfig(BaseModel):
    active: str = "jarvis"


class ConversationConfig(BaseModel):
    max_history: int = 50
    max_context_tokens: int = 8192
    autosave: bool = True
    autosave_interval: int = 60


class STTConfig(BaseModel):
    model_size: str = "base"
    device: str = "auto"
    compute_type: str = "auto"
    language: str = ""
    vad_threshold: float = 0.3
    min_speech_duration: float = 0.3


class TTSConfig(BaseModel):
    voice_dir: str = ""
    default_voice: str = "en_US-lessac-medium"
    sample_rate: int = 22050


class MemoryConfig(BaseModel):
    db_path: str = "memory.db"
    vector_db_path: str = "vector_memory"
    auto_extract: bool = True
    auto_extract_interval: int = 300
    max_facts_in_context: int = 20


class ToolPermissionConfig(BaseModel):
    level: Literal["auto", "confirm", "deny"] = "confirm"
    dangerous_operations: Literal["auto", "confirm", "deny"] = "confirm"


class ToolConfig(BaseModel):
    enabled: bool = True
    max_tool_rounds: int = 5
    permissions: dict[str, ToolPermissionConfig] = Field(default_factory=dict)


class LoggingConfig(BaseModel):
    level: Literal["debug", "info", "warning", "error"] = "info"
    format: Literal["console", "json"] = "console"


class EmailConfig(BaseModel):
    imap_host: str = ""
    imap_port: int = 993
    smtp_host: str = ""
    smtp_port: int = 587
    use_ssl: bool = True
    username: str = ""
    password: str = ""
    from_address: str = ""


class CalendarConfig(BaseModel):
    provider: Literal["local", "google"] = "local"
    db_path: str = "calendar.db"
    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""
    google_calendar_id: str = "primary"
    reminders_enabled: bool = True


class CallingConfig(BaseModel):
    provider: Literal["local", "twilio"] = "local"
    db_path: str = "calls.db"
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""


class NotesConfig(BaseModel):
    db_path: str = "notes.db"


class TelegramConfig(BaseModel):
    enabled: bool = False
    api_id: int = 0
    api_hash: str = ""
    session_name: str = "jarvis_telegram"
    allowed_users: list[int] = Field(default_factory=list)
    owner_chat_id: int = 0
    voice_enabled: bool = True


class ExternalConfig(BaseModel):
    weather_api_key: str = ""
    news_api_key: str = ""
    default_city: str = ""


class ServicesConfig(BaseModel):
    enabled: bool = True
    email: EmailConfig = Field(default_factory=EmailConfig)
    calendar: CalendarConfig = Field(default_factory=CalendarConfig)
    calling: CallingConfig = Field(default_factory=CallingConfig)
    notes: NotesConfig = Field(default_factory=NotesConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    external: ExternalConfig = Field(default_factory=ExternalConfig)


class AppConfig(BaseModel):
    llm: LLMProviderConfig = Field(default_factory=LLMProviderConfig)
    openrouter: OpenRouterConfig = Field(default_factory=OpenRouterConfig)
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig)
    gemini: GeminiConfig = Field(default_factory=GeminiConfig)
    sarvam: SarvamConfig = Field(default_factory=SarvamConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    personality: PersonalityConfig = Field(default_factory=PersonalityConfig)
    conversation: ConversationConfig = Field(default_factory=ConversationConfig)
    stt: STTConfig = Field(default_factory=STTConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    tool: ToolConfig = Field(default_factory=ToolConfig)
    services: ServicesConfig = Field(default_factory=ServicesConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


class ConfigManager:
    def __init__(self, config_path: str | Path | None = None):
        self.config_path = Path(config_path) if config_path else Path.cwd() / "config.yaml"
        self.config = self._load_config()

    def _load_config(self) -> AppConfig:
        config_data = self._load_yaml()
        config_data = self._apply_env_overrides(config_data)
        return AppConfig(**config_data)

    def _load_yaml(self) -> dict:
        if not self.config_path.exists():
            return {}
        with open(self.config_path) as f:
            return yaml.safe_load(f) or {}

    def _apply_env_overrides(self, config: dict) -> dict:
        provider = os.getenv("LLM_PROVIDER")
        if provider:
            config.setdefault("llm", {})["provider"] = provider

        model = os.getenv("LLM_MODEL")
        if model:
            config.setdefault("llm", {})["model"] = model

        active = os.getenv("ACTIVE_PERSONALITY")
        if active:
            config.setdefault("personality", {})["active"] = active

        api_key = os.getenv("OPENROUTER_API_KEY")
        if api_key:
            config.setdefault("openrouter", {})["api_key"] = api_key

        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            config.setdefault("openai", {})["api_key"] = api_key

        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            config.setdefault("gemini", {})["api_key"] = api_key

        api_key = os.getenv("SARVAM_API_KEY")
        if api_key:
            config.setdefault("sarvam", {})["api_key"] = api_key

        email_username = os.getenv("EMAIL_USERNAME")
        if email_username:
            config.setdefault("services", {}).setdefault("email", {})["username"] = email_username
        email_password = os.getenv("EMAIL_PASSWORD")
        if email_password:
            config.setdefault("services", {}).setdefault("email", {})["password"] = email_password
        email_imap = os.getenv("EMAIL_IMAP_HOST")
        if email_imap:
            config.setdefault("services", {}).setdefault("email", {})["imap_host"] = email_imap
        email_smtp = os.getenv("EMAIL_SMTP_HOST")
        if email_smtp:
            config.setdefault("services", {}).setdefault("email", {})["smtp_host"] = email_smtp
        email_from = os.getenv("EMAIL_FROM")
        if email_from:
            config.setdefault("services", {}).setdefault("email", {})["from_address"] = email_from

        weather_key = os.getenv("WEATHER_API_KEY")
        if weather_key:
            config.setdefault("services", {}).setdefault("external", {})["weather_api_key"] = weather_key
        news_key = os.getenv("NEWS_API_KEY")
        if news_key:
            config.setdefault("services", {}).setdefault("external", {})["news_api_key"] = news_key

        twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
        if twilio_sid:
            config.setdefault("services", {}).setdefault("calling", {})["twilio_account_sid"] = twilio_sid
        twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
        if twilio_token:
            config.setdefault("services", {}).setdefault("calling", {})["twilio_auth_token"] = twilio_token
        twilio_from = os.getenv("TWILIO_FROM_NUMBER")
        if twilio_from:
            config.setdefault("services", {}).setdefault("calling", {})["twilio_from_number"] = twilio_from

        google_client_id = os.getenv("GOOGLE_CLIENT_ID")
        if google_client_id:
            config.setdefault("services", {}).setdefault("calendar", {})["google_client_id"] = google_client_id
        google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        if google_client_secret:
            config.setdefault("services", {}).setdefault("calendar", {})["google_client_secret"] = google_client_secret
        google_refresh = os.getenv("GOOGLE_REFRESH_TOKEN")
        if google_refresh:
            config.setdefault("services", {}).setdefault("calendar", {})["google_refresh_token"] = google_refresh
        google_calendar = os.getenv("GOOGLE_CALENDAR_ID")
        if google_calendar:
            config.setdefault("services", {}).setdefault("calendar", {})["google_calendar_id"] = google_calendar

        telegram = config.setdefault("services", {}).setdefault("telegram", {})
        if os.getenv("TELEGRAM_API_ID"):
            telegram["api_id"] = int(os.getenv("TELEGRAM_API_ID"))
        if os.getenv("TELEGRAM_API_HASH"):
            telegram["api_hash"] = os.getenv("TELEGRAM_API_HASH")
        if os.getenv("TELEGRAM_SESSION_NAME"):
            telegram["session_name"] = os.getenv("TELEGRAM_SESSION_NAME")
        if os.getenv("TELEGRAM_ALLOWED_USERS"):
            telegram["allowed_users"] = [
                int(u.strip()) for u in os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",") if u.strip()
            ]
        if os.getenv("TELEGRAM_OWNER_CHAT_ID"):
            telegram["owner_chat_id"] = int(os.getenv("TELEGRAM_OWNER_CHAT_ID"))
        if os.getenv("TELEGRAM_ENABLED", "").lower() in ("1", "true", "yes"):
            telegram["enabled"] = True
        if os.getenv("TELEGRAM_VOICE_ENABLED", "").lower() in ("0", "false", "no"):
            telegram["voice_enabled"] = False

        return config

    def get_api_key(self) -> str | None:
        provider = self.config.llm.provider
        if provider == "openrouter":
            return self._get_key("OPENROUTER_API_KEY", "openrouter")
        if provider == "openai":
            return self._get_key("OPENAI_API_KEY", "openai")
        if provider == "gemini":
            return self._get_key("GEMINI_API_KEY", "gemini")
        return None

    def _get_key(self, env_var: str, config_section: str) -> str | None:
        key = os.getenv(env_var)
        if key:
            return key
        section = getattr(self.config, config_section, None)
        if section:
            return getattr(section, "api_key", None)
        return None

    def get_base_url(self) -> str:
        provider = self.config.llm.provider
        if provider == "openrouter":
            return self.config.openrouter.base_url
        if provider == "openai":
            return self.config.openai.base_url
        if provider == "gemini":
            return self.config.gemini.base_url
        return self.config.openrouter.base_url
