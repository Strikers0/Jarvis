from __future__ import annotations

import asyncio
import re
import unicodedata
from typing import Optional

import httpx


class SarvamSTT:
    BASE_URL = "https://api.sarvam.ai"

    def __init__(
        self,
        api_key: str,
        model: str = "saarika:v2.5",
        language_code: str = "unknown",
        with_translation: bool = True,
        max_retries: int = 1,
    ):
        self.api_key = api_key
        self.model = model
        self.language_code = language_code
        self.with_translation = with_translation
        self.max_retries = max_retries
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60)
        return self._client

    def _normalize_text(self, text: str) -> str:
        text = unicodedata.normalize("NFKC", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    async def transcribe(self, audio_data: bytes, language: str = "") -> str:
        lang = language or self.language_code
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                files = {
                    "file": ("audio.wav", audio_data, "audio/wav"),
                    "language_code": (None, lang),
                    "model": (None, self.model),
                }
                if self.with_translation:
                    files["with_translation"] = (None, "true")
                headers = {"api-subscription-key": self.api_key}
                resp = await self.client.post(
                    f"{self.BASE_URL}/speech-to-text",
                    files=files,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
                translation = data.get("translation", "")
                transcript = data.get("transcript", "")
                if self.with_translation and translation:
                    return self._normalize_text(translation)
                return self._normalize_text(transcript)
            except httpx.TimeoutException as e:
                last_error = e
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise RuntimeError("Sarvam STT timeout after retries")
            except httpx.HTTPStatusError as e:
                last_error = e
                if attempt < self.max_retries and e.response.status_code in (429, 502, 503, 504):
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"Sarvam STT API error: {e.response.status_code} {e.response.text}")
            except httpx.RequestError as e:
                last_error = e
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"Sarvam STT request failed: {e}")

        raise RuntimeError(f"Sarvam STT failed after {self.max_retries + 1} attempts")

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
