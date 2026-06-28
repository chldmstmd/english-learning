from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

from .prompts import (
    BATCH_TRANSLATION_PROMPT,
    TRANSLATION_PROMPT,
    build_sentence_blocks,
)
from .providers import (
    FallbackTranslator,
    TranslationProvider,
)


@dataclass(frozen=True)
class TranslationResult:
    translation: str
    is_fallback: bool = False


class TranslationEngineError(RuntimeError):
    pass


class TranslationProviderError(TranslationEngineError):
    pass


class TranslationResponseError(TranslationEngineError):
    pass


class TranslationUnavailableError(TranslationEngineError):
    pass


class TranslationEngine:
    def __init__(
        self,
        *,
        providers: Mapping[str, TranslationProvider],
        fallback_translator: FallbackTranslator | None = None,
        runtime_settings_loader: Callable[[], Mapping[str, object]] | None = None,
    ) -> None:
        self._providers = {key.lower(): value for key, value in providers.items()}
        self._fallback_translator = fallback_translator
        self._runtime_settings_loader = runtime_settings_loader or (lambda: {})

    def _runtime_settings(self) -> Mapping[str, object]:
        return self._runtime_settings_loader()

    def _provider_name(self) -> str:
        value = self._runtime_settings().get("ai_provider", "deepseek")
        return str(value or "deepseek").lower()

    def _provider(self) -> TranslationProvider:
        provider_name = self._provider_name()
        if provider_name == "google":
            provider_name = "gemini"
        try:
            return self._providers[provider_name]
        except KeyError as exc:
            raise TranslationProviderError(f"Unknown translation provider: {provider_name}") from exc

    def _fallback_enabled(self) -> bool:
        value = self._runtime_settings().get("use_free_translation_fallback", True)
        return bool(value)

    @staticmethod
    def _parse_json_object(text: str) -> dict:
        try:
            result = json.loads(text)
        except json.JSONDecodeError as exc:
            raise TranslationResponseError("Translation provider returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise TranslationResponseError(f"Expected dict response, got {type(result)}")
        return result

    async def translate_in_context(self, word: str, sentence: str) -> str:
        prompt = TRANSLATION_PROMPT.format(word=word, sentence=sentence)
        text = await self._provider().complete_json(
            prompt,
            max_tokens=200,
            temperature=0.1,
            timeout=5.0,
            request_kind="single",
        )
        result = self._parse_json_object(text)
        translation = result.get("translation")
        if not isinstance(translation, str):
            raise TranslationResponseError("Translation response is missing a string translation")
        return translation

    async def translate_in_context_with_fallback(self, word: str, sentence: str) -> TranslationResult:
        try:
            return TranslationResult(
                translation=await self.translate_in_context(word, sentence),
                is_fallback=False,
            )
        except Exception as exc:
            if not self._fallback_enabled() or self._fallback_translator is None:
                raise TranslationUnavailableError("AI translation unavailable") from exc
            try:
                translation = await self._fallback_translator.translate(word)
            except Exception as fallback_exc:
                raise TranslationUnavailableError("All translation services unavailable") from fallback_exc
            return TranslationResult(translation=translation, is_fallback=True)

    async def batch_translate_article(
        self,
        article_text: str,
        word_entries: Sequence[tuple[int, int, str]],
        sentences: Sequence[dict],
    ) -> dict[str, str]:
        prompt = BATCH_TRANSLATION_PROMPT.format(
            article_text=article_text,
            sentence_blocks=build_sentence_blocks(word_entries, sentences),
        )
        text = await self._provider().complete_json(
            prompt,
            max_tokens=16000,
            temperature=0.1,
            timeout=180.0,
            request_kind="batch",
        )
        result = self._parse_json_object(text)
        return {str(key): str(value) for key, value in result.items()}
