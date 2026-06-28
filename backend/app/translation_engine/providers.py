from __future__ import annotations

import asyncio
from typing import Any, Callable, Literal, Optional, Protocol

RequestKind = Literal["single", "batch"]


class TranslationProvider(Protocol):
    async def complete_json(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        timeout: float,
        request_kind: RequestKind,
    ) -> str:
        """Return a JSON string produced by a translation model."""


class FallbackTranslator(Protocol):
    async def translate(self, word: str) -> str:
        """Return a plain word translation from a fallback service."""


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        api_key_getter: Callable[[], str],
        model_getter: Callable[[], str],
        base_url_getter: Optional[Callable[[], str]] = None,
    ) -> None:
        self._api_key_getter = api_key_getter
        self._model_getter = model_getter
        self._base_url_getter = base_url_getter
        self._client: Any | None = None

    def _get_client(self) -> Any:
        from openai import AsyncOpenAI

        api_key = self._api_key_getter()
        if not api_key:
            raise RuntimeError("API key is not configured")
        if self._client is None:
            kwargs = {"api_key": api_key}
            if self._base_url_getter is not None:
                kwargs["base_url"] = self._base_url_getter()
            self._client = AsyncOpenAI(**kwargs)
        return self._client

    async def complete_json(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        timeout: float,
        request_kind: RequestKind,
    ) -> str:
        response = await asyncio.wait_for(
            self._get_client().chat.completions.create(
                model=self._model_getter(),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
                response_format={"type": "json_object"},
            ),
            timeout=timeout,
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("Translation provider returned an empty response")
        return content


class GeminiProvider:
    def __init__(
        self,
        *,
        api_key_getter: Callable[[], str],
        single_model: str = "models/gemini-3.1-flash-lite",
        batch_model: str = "models/gemini-3.5-flash",
    ) -> None:
        self._api_key_getter = api_key_getter
        self._single_model = single_model
        self._batch_model = batch_model
        self._client: Any | None = None

    def _get_client(self) -> Any:
        from google import genai

        api_key = self._api_key_getter()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        if self._client is None:
            self._client = genai.Client(api_key=api_key)
        return self._client

    async def complete_json(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        timeout: float,
        request_kind: RequestKind,
    ) -> str:
        from google.genai import types

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            max_output_tokens=max_tokens,
            temperature=temperature,
        )
        model = self._batch_model if request_kind == "batch" else self._single_model
        response = await asyncio.wait_for(
            self._get_client().aio.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            ),
            timeout=timeout,
        )
        if not response.text:
            raise RuntimeError("Translation provider returned an empty response")
        return response.text


class GoogleFallbackTranslator:
    async def translate(self, word: str) -> str:
        from deep_translator import GoogleTranslator

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: GoogleTranslator(source="en", target="zh-CN").translate(word),
        )
