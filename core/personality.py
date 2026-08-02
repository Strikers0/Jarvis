from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from personalities.base import Personality
from personalities.female import FEMALE_PERSONALITIES
from personalities.male import MALE_PERSONALITIES

ALL_PERSONALITIES: dict[str, Personality] = {}
ALL_PERSONALITIES.update(MALE_PERSONALITIES)
ALL_PERSONALITIES.update(FEMALE_PERSONALITIES)


class PersonalityManager:
    def __init__(
        self,
        custom_path: str | Path | None = None,
        voice_store_path: str | Path | None = None,
    ):
        self._personalities: dict[str, Personality] = dict(ALL_PERSONALITIES)
        self._active: Optional[Personality] = None
        self._custom_path = Path(custom_path) if custom_path else None
        self._voice_store_path = (
            Path(voice_store_path)
            if voice_store_path
            else Path("runtime") / "personality_voices.json"
        )
        self._voice_overrides: dict[str, str] = {}
        self._load_custom_personalities()
        self._load_voice_overrides()

    def _load_voice_overrides(self) -> None:
        from voice.sarvam_voices import is_valid_voice
        try:
            if self._voice_store_path.exists():
                with open(self._voice_store_path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    for name, voice in data.items():
                        if is_valid_voice(voice):
                            self._voice_overrides[name] = voice.lower()
        except (OSError, ValueError):
            self._voice_overrides = {}

    def _save_voice_overrides(self) -> None:
        try:
            self._voice_store_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._voice_store_path, "w", encoding="utf-8") as f:
                json.dump(self._voice_overrides, f, indent=2)
        except OSError:
            pass

    def _load_custom_personalities(self) -> None:
        if not self._custom_path or not self._custom_path.exists():
            return
        if self._custom_path.is_file() and self._custom_path.suffix in (".yaml", ".yml"):
            self._load_personality_file(self._custom_path)
        elif self._custom_path.is_dir():
            for f in self._custom_path.glob("*.yaml") or self._custom_path.glob("*.yml"):
                self._load_personality_file(f)

    def _load_personality_file(self, path: Path) -> None:
        import yaml
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
            if isinstance(data, list):
                for item in data:
                    self._add_personality(item)
            elif isinstance(data, dict):
                if "name" in data:
                    self._add_personality(data)
                else:
                    for item in data.values():
                        if isinstance(item, dict) and "name" in item:
                            self._add_personality(item)
        except Exception:
            pass

    def _add_personality(self, data: dict) -> None:
        try:
            personality = Personality.from_dict(data)
            self._personalities[personality.name] = personality
        except (KeyError, ValueError):
            pass

    def set_active(self, name: str) -> Optional[Personality]:
        personality = self.get(name)
        if personality:
            self._active = personality
        return personality

    def get_active(self) -> Optional[Personality]:
        return self._active

    def get(self, name: str) -> Optional[Personality]:
        name_lower = name.lower().replace(" ", "_")
        for key, p in self._personalities.items():
            if key == name_lower:
                return p
        result = self._personalities.get(name)
        if result:
            return result
        for key, p in self._personalities.items():
            if key.lower() == name_lower:
                return p
        return None

    def list(self) -> list[Personality]:
        return list(self._personalities.values())

    def list_names(self) -> list[str]:
        return list(self._personalities.keys())

    def add(self, personality: Personality) -> None:
        self._personalities[personality.name] = personality

    def remove(self, name: str) -> bool:
        if name in ALL_PERSONALITIES:
            return False
        return self._personalities.pop(name, None) is not None

    def get_sarvam_voice(self, name: Optional[str] = None) -> str:
        from voice.sarvam_voices import is_valid_voice, resolve_voice
        personality = self.get(name) if name else self.get_active()
        if personality is None:
            return "shubh"
        voice = self._voice_overrides.get(personality.name)
        if voice:
            return voice
        if personality.sarvam_voice and is_valid_voice(personality.sarvam_voice):
            return personality.sarvam_voice
        return resolve_voice(personality.gender)

    def set_sarvam_voice(self, name: str, voice: str) -> bool:
        from voice.sarvam_voices import is_valid_voice
        personality = self.get(name)
        if personality is None or not is_valid_voice(voice):
            return False
        self._voice_overrides[personality.name] = voice.lower()
        personality.sarvam_voice = voice.lower()
        self._save_voice_overrides()
        return True
