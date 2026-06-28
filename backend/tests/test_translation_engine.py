from __future__ import annotations

import asyncio
import importlib
import shutil
import sys
from pathlib import Path

import pytest

from app.translation_engine import OpenAICompatibleProvider
from app.translation_engine.engine import TranslationEngine, TranslationUnavailableError


class FakeProvider:
    def __init__(self, response: str = "", error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict] = []

    async def complete_json(self, prompt: str, **kwargs) -> str:
        self.calls.append({"prompt": prompt, **kwargs})
        if self.error:
            raise self.error
        return self.response


class FakeFallback:
    def __init__(self, translation: str) -> None:
        self.translation = translation
        self.calls: list[dict] = []

    async def translate(
        self,
        word: str,
        source_language: str = "en",
        target_language: str = "zh-CN",
    ) -> str:
        self.calls.append({
            "word": word,
            "source_language": source_language,
            "target_language": target_language,
        })
        return self.translation


class FakeOpenAIMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeOpenAIChoice:
    def __init__(self, content: str) -> None:
        self.message = FakeOpenAIMessage(content)


class FakeOpenAIResponse:
    def __init__(self, content: str) -> None:
        self.choices = [FakeOpenAIChoice(content)]


class FakeOpenAICompletions:
    def __init__(self, content: str = '{"translation": "河岸"}') -> None:
        self.content = content
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeOpenAIResponse(self.content)


class FakeOpenAIChat:
    def __init__(self, completions: FakeOpenAICompletions) -> None:
        self.completions = completions


class FakeOpenAIClient:
    def __init__(self, completions: FakeOpenAICompletions) -> None:
        self.chat = FakeOpenAIChat(completions)


def test_translate_in_context_returns_provider_translation():
    provider = FakeProvider('{"translation": "银行"}')
    engine = TranslationEngine(
        providers={"deepseek": provider},
        runtime_settings_loader=lambda: {"ai_provider": "deepseek"},
    )

    result = asyncio.run(engine.translate_in_context("bank", "the bank approved the loan"))

    assert result == "银行"
    assert provider.calls[0]["request_kind"] == "single"
    assert provider.calls[0]["max_tokens"] == 100
    assert provider.calls[0]["temperature"] == 0
    assert "从en翻译成zh-CN" in provider.calls[0]["prompt"]
    assert "逐词ruby标注" in provider.calls[0]["prompt"]
    assert "只翻译目标单词本身" in provider.calls[0]["prompt"]
    assert "不要翻译包含它的相邻短语" in provider.calls[0]["prompt"]
    assert "University Press" in provider.calls[0]["prompt"]
    assert "the bank approved the loan" in provider.calls[0]["prompt"]


def test_translate_in_context_accepts_custom_languages():
    provider = FakeProvider('{"translation": "rive"}')
    engine = TranslationEngine(
        providers={"deepseek": provider},
        runtime_settings_loader=lambda: {"ai_provider": "deepseek"},
    )

    result = asyncio.run(
        engine.translate_in_context(
            "bank",
            "The boat reached the bank of the river.",
            source_language="en",
            target_language="fr",
        )
    )

    assert result == "rive"
    assert "从en翻译成fr" in provider.calls[0]["prompt"]


def test_translate_with_fallback_marks_fallback_result():
    provider = FakeProvider(error=RuntimeError("provider down"))
    fallback = FakeFallback("河岸")
    engine = TranslationEngine(
        providers={"deepseek": provider},
        fallback_translator=fallback,
        runtime_settings_loader=lambda: {
            "ai_provider": "deepseek",
            "use_free_translation_fallback": True,
        },
    )

    result = asyncio.run(
        engine.translate_in_context_with_fallback("bank", "by the bank of the river")
    )

    assert result.translation == "河岸"
    assert result.is_fallback is True
    assert fallback.calls == [
        {
            "word": "bank",
            "source_language": "en",
            "target_language": "zh-CN",
        }
    ]


def test_translate_with_fallback_passes_custom_languages():
    provider = FakeProvider(error=RuntimeError("provider down"))
    fallback = FakeFallback("rive")
    engine = TranslationEngine(
        providers={"deepseek": provider},
        fallback_translator=fallback,
        runtime_settings_loader=lambda: {
            "ai_provider": "deepseek",
            "use_free_translation_fallback": True,
        },
    )

    result = asyncio.run(
        engine.translate_in_context_with_fallback(
            "bank",
            "The boat reached the bank of the river.",
            source_language="en",
            target_language="fr",
        )
    )

    assert result.translation == "rive"
    assert result.is_fallback is True
    assert fallback.calls == [
        {
            "word": "bank",
            "source_language": "en",
            "target_language": "fr",
        }
    ]


def test_translate_with_disabled_fallback_raises_unavailable():
    provider = FakeProvider(error=RuntimeError("provider down"))
    engine = TranslationEngine(
        providers={"deepseek": provider},
        fallback_translator=FakeFallback("河岸"),
        runtime_settings_loader=lambda: {
            "ai_provider": "deepseek",
            "use_free_translation_fallback": False,
        },
    )

    with pytest.raises(TranslationUnavailableError, match="AI translation unavailable"):
        asyncio.run(engine.translate_in_context_with_fallback("bank", "by the bank"))


def test_batch_translate_normalizes_response_values_to_strings():
    provider = FakeProvider('{"0_1": "银行", "0_2": 5}')
    engine = TranslationEngine(
        providers={"deepseek": provider},
        runtime_settings_loader=lambda: {"ai_provider": "deepseek"},
    )

    result = asyncio.run(
        engine.batch_translate_article(
            "The bank approved five loans.",
            [(0, 1, "bank"), (0, 2, "approved")],
            [{"index": 0, "text": "The bank approved five loans."}],
        )
    )

    assert result == {"0_1": "银行", "0_2": "5"}
    assert provider.calls[0]["request_kind"] == "batch"
    assert provider.calls[0]["max_tokens"] == 16000


def test_openai_compatible_provider_adds_extra_body_to_single_requests():
    completions = FakeOpenAICompletions()
    provider = OpenAICompatibleProvider(
        api_key_getter=lambda: "key",
        model_getter=lambda: "model",
        single_request_extra_body={"thinking": {"type": "disabled"}},
    )
    provider._client = FakeOpenAIClient(completions)

    result = asyncio.run(
        provider.complete_json(
            "prompt",
            max_tokens=100,
            temperature=0,
            timeout=1,
            request_kind="single",
        )
    )

    assert result == '{"translation": "河岸"}'
    assert completions.calls[0]["extra_body"] == {"thinking": {"type": "disabled"}}


def test_openai_compatible_provider_omits_single_extra_body_for_batch_requests():
    completions = FakeOpenAICompletions()
    provider = OpenAICompatibleProvider(
        api_key_getter=lambda: "key",
        model_getter=lambda: "model",
        single_request_extra_body={"thinking": {"type": "disabled"}},
    )
    provider._client = FakeOpenAIClient(completions)

    asyncio.run(
        provider.complete_json(
            "prompt",
            max_tokens=16000,
            temperature=0.1,
            timeout=1,
            request_kind="batch",
        )
    )

    assert "extra_body" not in completions.calls[0]


def test_openai_compatible_provider_omits_extra_body_by_default():
    completions = FakeOpenAICompletions()
    provider = OpenAICompatibleProvider(
        api_key_getter=lambda: "key",
        model_getter=lambda: "model",
    )
    provider._client = FakeOpenAIClient(completions)

    asyncio.run(
        provider.complete_json(
            "prompt",
            max_tokens=100,
            temperature=0,
            timeout=1,
            request_kind="single",
        )
    )

    assert "extra_body" not in completions.calls[0]


def test_translation_engine_package_can_be_imported_standalone(tmp_path, monkeypatch):
    source_dir = Path(__file__).resolve().parents[1] / "app" / "translation_engine"
    package_dir = tmp_path / "translation_engine"
    shutil.copytree(
        source_dir,
        package_dir,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("translation_engine", None)

    module = importlib.import_module("translation_engine")
    engine = module.TranslationEngine(
        providers={"deepseek": FakeProvider('{"translation": "银行"}')},
        runtime_settings_loader=lambda: {"ai_provider": "deepseek"},
    )

    result = asyncio.run(engine.translate_in_context("bank", "the bank approved the loan"))

    assert result == "银行"
