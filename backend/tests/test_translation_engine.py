from __future__ import annotations

import asyncio
import importlib
import shutil
import sys
from pathlib import Path

import pytest

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
        self.words: list[str] = []

    async def translate(self, word: str) -> str:
        self.words.append(word)
        return self.translation


def test_translate_in_context_returns_provider_translation():
    provider = FakeProvider('{"translation": "银行"}')
    engine = TranslationEngine(
        providers={"deepseek": provider},
        runtime_settings_loader=lambda: {"ai_provider": "deepseek"},
    )

    result = asyncio.run(engine.translate_in_context("bank", "the bank approved the loan"))

    assert result == "银行"
    assert provider.calls[0]["request_kind"] == "single"
    assert "the bank approved the loan" in provider.calls[0]["prompt"]


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

    result = asyncio.run(engine.translate_in_context_with_fallback("bank", "by the bank of the river"))

    assert result.translation == "河岸"
    assert result.is_fallback is True
    assert fallback.words == ["bank"]


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
