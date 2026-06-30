from __future__ import annotations

from collections.abc import Mapping

from translation_engine import (
    GeminiProvider,
    GoogleFallbackTranslator,
    OpenAICompatibleProvider,
    TranslationEngine,
)

from .config import settings
from .mock_provider import MockTranslationProvider


VALID_PROVIDERS = frozenset({"deepseek", "openai", "gemini", "google"})


def normalize_provider_name(provider_name: str) -> str:
    value = str(provider_name or "deepseek").lower()
    return "gemini" if value == "google" else value


def create_translation_engine(runtime_settings: Mapping[str, object]) -> TranslationEngine:
    if settings.translation_engine_mock:
        mock_provider = MockTranslationProvider()
        return TranslationEngine(
            providers={
                "deepseek": mock_provider,
                "openai": mock_provider,
                "gemini": mock_provider,
            },
            runtime_settings_loader=lambda: runtime_settings,
        )

    return TranslationEngine(
        providers={
            "deepseek": OpenAICompatibleProvider(
                api_key_getter=lambda: settings.deepseek_api_key,
                model_getter=lambda: settings.deepseek_model,
                base_url_getter=lambda: settings.deepseek_base_url,
                single_request_extra_body={"thinking": {"type": "disabled"}},
            ),
            "openai": OpenAICompatibleProvider(
                api_key_getter=lambda: settings.openai_api_key,
                model_getter=lambda: "gpt-4o",
            ),
            "gemini": GeminiProvider(api_key_getter=lambda: settings.gemini_api_key),
        },
        fallback_translator=GoogleFallbackTranslator(),
        runtime_settings_loader=lambda: runtime_settings,
    )
