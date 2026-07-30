from __future__ import annotations

import base64
from pathlib import Path
from typing import AsyncGenerator, Optional

import httpx


class SarvamTTS:
    BASE_URL = "https://api.sarvam.ai"

    def __init__(
        self,
        api_key: str,
        model: str = "bulbul:v3",
        language_code: str = "hi-IN",
        voice: str = "priya",
        speed: float = 1.0,
        format: str = "wav",
    ):
        self.api_key = api_key
        self.model = model
        self.language_code = language_code
        self.voice = voice
        self.speed = speed
        self.format = format
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=120)
        return self._client

    async def synthesize(self, text: str, output_path: str | Path = "runtime/response.wav") -> Path:
        payload = {
            "inputs": [text],
            "target_language_code": self.language_code,
            "speaker": self.voice,
            "pace": self.speed,
            "model": self.model,
        }
        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json",
        }
        try:
            resp = await self.client.post(
                f"{self.BASE_URL}/text-to-speech",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            audios = data.get("audios", [])
            if not audios:
                raise RuntimeError("Sarvam TTS returned no audio data")
            audio_bytes = base64.b64decode(audios[0])
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(audio_bytes)
            return out
        except httpx.TimeoutException:
            raise RuntimeError("Sarvam TTS timeout")
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"Sarvam TTS API error: {e.response.status_code} {e.response.text}")

    async def synthesize_stream(
        self, text: str, voice: str = ""
    ) -> AsyncGenerator[bytes, None]:
        payload = {
            "inputs": [text],
            "target_language_code": self.language_code,
            "speaker": voice or self.voice,
            "pace": self.speed,
            "model": self.model,
        }
        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json",
        }
        try:
            resp = await self.client.post(
                f"{self.BASE_URL}/text-to-speech",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            audios = data.get("audios", [])
            if audios:
                yield base64.b64decode(audios[0])
        except httpx.TimeoutException:
            raise RuntimeError("Sarvam TTS timeout")
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"Sarvam TTS API error: {e.response.status_code} {e.response.text}")

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
