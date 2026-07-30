from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


Gender = Literal["male", "female"]


@dataclass
class PersonalityTraits:
    tone: str = "neutral"
    vocabulary: str = "standard"
    humor_style: str = "none"
    formality: Literal["formal", "casual", "neutral"] = "neutral"


@dataclass
class Personality:
    name: str
    gender: Gender
    description: str
    system_prompt: str
    traits: PersonalityTraits = field(default_factory=PersonalityTraits)
    voice_id: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> Personality:
        traits_data = data.get("traits", {})
        traits = PersonalityTraits(
            tone=traits_data.get("tone", "neutral"),
            vocabulary=traits_data.get("vocabulary", "standard"),
            humor_style=traits_data.get("humor_style", "none"),
            formality=traits_data.get("formality", "neutral"),
        )
        return cls(
            name=data["name"],
            gender=data["gender"],
            description=data.get("description", ""),
            system_prompt=data["system_prompt"],
            traits=traits,
            voice_id=data.get("voice_id", ""),
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "gender": self.gender,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "traits": {
                "tone": self.traits.tone,
                "vocabulary": self.traits.vocabulary,
                "humor_style": self.traits.humor_style,
                "formality": self.traits.formality,
            },
            "voice_id": self.voice_id,
        }
