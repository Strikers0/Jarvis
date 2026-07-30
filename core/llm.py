from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Callable, Optional

import httpx


@dataclass
class LLMMessage:
    role: str  # "system", "user", "assistant", "tool"
    content: str
    tool_calls: Optional[list[dict]] = None
    tool_call_id: Optional[str] = None


@dataclass
class LLMResponse:
    content: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"
    tool_calls: Optional[list[dict]] = None


@dataclass
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0

    def add(self, other: LLMUsage) -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.total_tokens += other.total_tokens
        self.cost += other.cost


TOKEN_COST_PER_MILLION: dict[str, tuple[float, float]] = {
    "openai/gpt-4o-mini": (0.150, 0.600),
    "openai/gpt-4o": (2.500, 10.000),
    "openrouter/default": (0.150, 0.600),
}

MODEL_PATTERNS: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.150, 0.600),
    "gpt-4o": (2.500, 10.000),
    "claude": (3.000, 15.000),
    "gemini": (0.500, 1.500),
    "mistral": (0.200, 0.600),
    "llama": (0.100, 0.400),
}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    if model in TOKEN_COST_PER_MILLION:
        input_cost, output_cost = TOKEN_COST_PER_MILLION[model]
    else:
        input_cost, output_cost = MODEL_PATTERNS.get("gpt-4o-mini", (0.150, 0.600))
        for pattern, costs in MODEL_PATTERNS.items():
            if pattern in model:
                input_cost, output_cost = costs
                break
    return (prompt_tokens / 1_000_000 * input_cost) + (completion_tokens / 1_000_000 * output_cost)


class LLMProvider(ABC):
    def __init__(self, api_key: str, base_url: str, config: Any):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None
        self.usage = LLMUsage()

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.config.llm.timeout)
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _build_messages(self, messages: list[LLMMessage], system_prompt: str) -> list[dict]:
        result = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            entry: dict[str, Any] = {"role": msg.role, "content": msg.content}
            if msg.tool_calls:
                entry["tool_calls"] = msg.tool_calls
            if msg.tool_call_id:
                entry["tool_call_id"] = msg.tool_call_id
            result.append(entry)
        return result

    def _update_usage(self, response_data: dict) -> None:
        usage = response_data.get("usage", {})
        prompt = usage.get("prompt_tokens", 0)
        completion = usage.get("completion_tokens", 0)
        model = response_data.get("model", self.config.llm.model)
        cost = estimate_cost(model, prompt, completion)
        self.usage.add(LLMUsage(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
            cost=cost,
        ))

    @abstractmethod
    async def chat(
        self,
        messages: list[LLMMessage],
        system_prompt: str = "",
        tools: Optional[list[dict]] = None,
    ) -> LLMResponse:
        ...

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[LLMMessage],
        system_prompt: str = "",
        tools: Optional[list[dict]] = None,
    ) -> AsyncGenerator[str, None]:
        ...

    async def _execute_with_retry(self, func: Callable, **kwargs) -> Any:
        last_error = None
        for attempt in range(self.config.llm.retry_attempts):
            try:
                return await func(**kwargs)
            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code in (429, 503):
                    delay = self.config.llm.retry_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
                    continue
                raise
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_error = e
                if attempt < self.config.llm.retry_attempts - 1:
                    delay = self.config.llm.retry_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
                    continue
                raise
        raise last_error


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, api_key: str, base_url: str, config: Any):
        super().__init__(api_key, base_url, config)
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def chat(
        self,
        messages: list[LLMMessage],
        system_prompt: str = "",
        tools: Optional[list[dict]] = None,
    ) -> LLMResponse:
        async def _do_chat() -> dict:
            payload = self._build_payload(messages, system_prompt, tools, stream=False)
            resp = await self.client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers,
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()

        data = await self._execute_with_retry(_do_chat)
        self._update_usage(data)
        choice = data["choices"][0]
        msg = choice["message"]
        return LLMResponse(
            content=msg.get("content", "") or "",
            model=data.get("model", self.config.llm.model),
            usage=data.get("usage", {}),
            finish_reason=choice.get("finish_reason", "stop"),
            tool_calls=msg.get("tool_calls"),
        )

    async def chat_stream(
        self,
        messages: list[LLMMessage],
        system_prompt: str = "",
        tools: Optional[list[dict]] = None,
    ) -> AsyncGenerator[str, None]:
        payload = self._build_payload(messages, system_prompt, tools, stream=True)
        async with httpx.AsyncClient(timeout=self.config.llm.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._headers,
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    if choices := data.get("choices"):
                        delta = choices[0].get("delta", {})
                        if content := delta.get("content"):
                            yield content

    def _build_payload(
        self,
        messages: list[LLMMessage],
        system_prompt: str,
        tools: Optional[list[dict]],
        stream: bool,
    ) -> dict:
        payload: dict[str, Any] = {
            "model": self.config.llm.model,
            "messages": self._build_messages(messages, system_prompt),
            "temperature": self.config.llm.temperature,
            "max_tokens": self.config.llm.max_tokens,
            "stream": stream,
        }
        if tools:
            payload["tools"] = tools
        return payload


class OpenRouterProvider(OpenAICompatibleProvider):
    def __init__(self, api_key: str, base_url: str, config: Any):
        super().__init__(api_key, base_url, config)
        self._headers["HTTP-Referer"] = "https://github.com/jarvis-assistant"
        self._headers["X-Title"] = "JARVIS Assistant"


class OpenAIProvider(OpenAICompatibleProvider):
    pass


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, base_url: str, config: Any):
        super().__init__(api_key, base_url, config)
        self._headers = {
            "X-Goog-Api-Key": api_key,
            "Content-Type": "application/json",
        }

    async def chat(
        self,
        messages: list[LLMMessage],
        system_prompt: str = "",
        tools: Optional[list[dict]] = None,
    ) -> LLMResponse:
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": self._build_gemini_contents(messages),
            "generationConfig": {
                "temperature": self.config.llm.temperature,
                "maxOutputTokens": self.config.llm.max_tokens,
            },
        }
        if tools:
            payload["tools"] = tools

        async def _do_chat() -> dict:
            url = f"{self.base_url}/models/{self.config.llm.model}:generateContent"
            resp = await self.client.post(url, headers=self._headers, json=payload)
            resp.raise_for_status()
            return resp.json()

        data = await self._execute_with_retry(_do_chat)
        candidate = data.get("candidates", [{}])[0]
        parts = candidate.get("content", {}).get("parts", [])
        content = ""
        tool_calls = None
        for part in parts:
            if "text" in part:
                content = part["text"]
            if "functionCall" in part:
                fc = part["functionCall"]
                tool_calls = [{
                    "id": f"call_{fc.get('name', 'unknown')}",
                    "type": "function",
                    "function": {
                        "name": fc.get("name", ""),
                        "arguments": json.dumps(fc.get("args", {})),
                    },
                }]
        usage = data.get("usageMetadata", {})
        return LLMResponse(
            content=content,
            model=data.get("model", self.config.llm.model),
            usage={
                "prompt_tokens": usage.get("promptTokenCount", 0),
                "completion_tokens": usage.get("candidatesTokenCount", 0),
                "total_tokens": usage.get("totalTokenCount", 0),
            },
            finish_reason=candidate.get("finishReason", "stop"),
            tool_calls=tool_calls,
        )

    async def chat_stream(
        self,
        messages: list[LLMMessage],
        system_prompt: str = "",
        tools: Optional[list[dict]] = None,
    ) -> AsyncGenerator[str, None]:
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": self._build_gemini_contents(messages),
            "generationConfig": {
                "temperature": self.config.llm.temperature,
                "maxOutputTokens": self.config.llm.max_tokens,
            },
        }
        if tools:
            payload["tools"] = tools

        url = f"{self.base_url}/models/{self.config.llm.model}:streamGenerateContent?alt=sse"
        async with httpx.AsyncClient(timeout=self.config.llm.timeout) as client:
            async with client.stream("POST", url, headers=self._headers, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        data = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue
                    for candidate in data.get("candidates", []):
                        for part in candidate.get("content", {}).get("parts", []):
                            if text := part.get("text"):
                                yield text

    def _build_gemini_contents(self, messages: list[LLMMessage]) -> list[dict]:
        contents = []
        for msg in messages:
            role = "user" if msg.role in ("user", "system") else "model"
            contents.append({
                "role": role,
                "parts": [{"text": msg.content}],
            })
        return contents


class LLMFactory:
    @staticmethod
    def create(config: Any) -> LLMProvider:
        provider_name = config.llm.provider
        api_key = get_api_key(config)
        base_url = get_base_url(config)

        if not api_key:
            raise ValueError(
                f"No API key found for provider '{provider_name}'. "
                f"Set the {provider_name.upper()}_API_KEY environment variable."
            )

        providers = {
            "openrouter": OpenRouterProvider,
            "openai": OpenAIProvider,
            "gemini": GeminiProvider,
        }

        provider_class = providers.get(provider_name)
        if not provider_class:
            raise ValueError(f"Unknown LLM provider: {provider_name}")

        return provider_class(api_key, base_url, config)


def get_api_key(config: Any) -> str | None:
    import os
    provider = config.llm.provider
    env_var = f"{provider.upper()}_API_KEY"
    key = os.getenv(env_var)
    if key:
        return key
    section = getattr(config, provider, None)
    if section and hasattr(section, "api_key"):
        return section.api_key
    return None


def get_base_url(config: Any) -> str:
    provider = config.llm.provider
    section = getattr(config, provider, None)
    if section and hasattr(section, "base_url"):
        return section.base_url
    return f"https://api.{provider}.com/v1"
