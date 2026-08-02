from __future__ import annotations

from typing import Optional

"""Sarvam AI Bulbul v3 TTS voice catalog.

Speaker names are case-sensitive and must be lowercase.
https://docs.sarvam.ai/api/api-guides-tutorials/text-to-speech/voices
"""

SARVAM_TTS_MODEL = "bulbul:v3"

MALE_VOICES: list[str] = [
    "shubh",
    "aditya",
    "rahul",
    "rohan",
    "amit",
    "dev",
    "ratan",
    "varun",
    "manan",
    "sumit",
    "kabir",
    "aayan",
    "ashutosh",
    "advait",
    "anand",
    "tarun",
    "sunny",
    "mani",
    "gokul",
    "vijay",
    "mohit",
    "rehan",
    "soham",
]

FEMALE_VOICES: list[str] = [
    "ritu",
    "priya",
    "neha",
    "pooja",
    "simran",
    "kavya",
    "ishita",
    "shreya",
    "roopa",
    "tanya",
    "shruti",
    "suhani",
    "kavitha",
    "rupali",
]

ALL_VOICES: list[str] = MALE_VOICES + FEMALE_VOICES

DEFAULT_MALE_VOICE = "shubh"
DEFAULT_FEMALE_VOICE = "ishita"


def is_valid_voice(voice: str) -> bool:
    return voice.lower() in ALL_VOICES


def voices_for_gender(gender: str) -> list[str]:
    if gender == "female":
        return FEMALE_VOICES
    return MALE_VOICES


def default_voice_for_gender(gender: str) -> str:
    return DEFAULT_FEMALE_VOICE if gender == "female" else DEFAULT_MALE_VOICE


def resolve_voice(gender: str, voice: Optional[str] = None) -> str:
    """Resolve a voice for a gender, validating against the Sarvam catalog."""
    if voice and is_valid_voice(voice):
        return voice.lower()
    return default_voice_for_gender(gender)
