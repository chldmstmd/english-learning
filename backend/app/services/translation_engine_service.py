from __future__ import annotations

from typing import Sequence

from app.config import settings
from app.services import settings_service
from app.translation_engine import (
    GeminiProvider,
    GoogleFallbackTranslator,
    OpenAICompatibleProvider,
    TranslationEngine,
    TranslationResult,
)


def create_default_translation_engine() -> TranslationEngine:
    return TranslationEngine(
        providers={
            "deepseek": OpenAICompatibleProvider(
                api_key_getter=lambda: settings.deepseek_api_key,
                model_getter=lambda: settings.deepseek_model,
                base_url_getter=lambda: settings.deepseek_base_url,
            ),
            "openai": OpenAICompatibleProvider(
                api_key_getter=lambda: settings.openai_api_key,
                model_getter=lambda: "gpt-4o",
            ),
            "gemini": GeminiProvider(api_key_getter=lambda: settings.gemini_api_key),
        },
        fallback_translator=GoogleFallbackTranslator(),
        runtime_settings_loader=settings_service.load,
    )


_default_engine: TranslationEngine | None = None


def get_translation_engine() -> TranslationEngine:
    global _default_engine
    if _default_engine is None:
        _default_engine = create_default_translation_engine()
    return _default_engine


async def translate_in_context(
    word: str,
    sentence: str,
    source_language: str = "en",
    target_language: str = "zh-CN",
) -> str:
    return await get_translation_engine().translate_in_context(
        word,
        sentence,
        source_language=source_language,
        target_language=target_language,
    )


async def translate_in_context_with_fallback(
    word: str,
    sentence: str,
    source_language: str = "en",
    target_language: str = "zh-CN",
) -> TranslationResult:
    return await get_translation_engine().translate_in_context_with_fallback(
        word,
        sentence,
        source_language=source_language,
        target_language=target_language,
    )


async def batch_translate_article(
    article_text: str,
    word_entries: Sequence[tuple[int, int, str]],
    sentences: Sequence[dict],
) -> dict[str, str]:
    return await get_translation_engine().batch_translate_article(article_text, word_entries, sentences)
