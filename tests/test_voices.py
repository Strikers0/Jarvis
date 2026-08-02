from __future__ import annotations

import pytest

from core.personality import PersonalityManager
from voice.sarvam_voices import (
    ALL_VOICES,
    FEMALE_VOICES,
    MALE_VOICES,
    default_voice_for_gender,
    is_valid_voice,
    resolve_voice,
    voices_for_gender,
)


def test_voice_catalog_is_lowercase_and_unique():
    assert len(set(ALL_VOICES)) == len(ALL_VOICES)
    assert all(v.islower() for v in ALL_VOICES)
    assert not set(MALE_VOICES) & set(FEMALE_VOICES)


def test_voices_for_gender():
    assert set(voices_for_gender("male")) == set(MALE_VOICES)
    assert set(voices_for_gender("female")) == set(FEMALE_VOICES)


def test_is_valid_voice():
    assert is_valid_voice("shubh")
    assert is_valid_voice("ishita")
    assert not is_valid_voice("gandalf")
    assert not is_valid_voice("")


def test_resolve_voice_defaults():
    assert resolve_voice("male", None) == default_voice_for_gender("male")
    assert resolve_voice("female", None) == default_voice_for_gender("female")
    assert resolve_voice("male", "SHUBH") == "shubh"


def test_personality_default_sarvam_voices_match_gender():
    manager = PersonalityManager()
    for p in manager.list():
        voice = manager.get_sarvam_voice(p.name)
        assert voice in (MALE_VOICES if p.gender == "male" else FEMALE_VOICES)


@pytest.fixture
def manager(tmp_path):
    return PersonalityManager(voice_store_path=tmp_path / "voices.json")


def test_set_and_get_sarvam_voice(manager):
    assert manager.set_sarvam_voice("jarvis", "ADITYA")
    assert manager.get_sarvam_voice("jarvis") == "aditya"


def test_set_invalid_voice_rejected(manager):
    assert not manager.set_sarvam_voice("jarvis", "gandalf")


def test_voice_override_persists(tmp_path):
    store = tmp_path / "voices.json"
    manager = PersonalityManager(voice_store_path=store)
    manager.set_sarvam_voice("kaaya", "neha")
    reloaded = PersonalityManager(voice_store_path=store)
    assert reloaded.get_sarvam_voice("kaaya") == "neha"
