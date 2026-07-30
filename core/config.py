from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, Optional

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
    tts_speaker: str = "meera"
    tts_pitch: float = 0.0
    tts_pace: float = 1.0
    tts_loudness: float = 1.0
    tts_sample_rate: int = 22050


class VoiceConfig(BaseModel):
    provider: Literal["whisper", "sarvam"] = "whisper"
    stt_provider: Literal["whisper", "sarvam"] = "whisper"
    tts_provider: Literal["piper", "sarvam"] = "piper"


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
