from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.services import translation_engine_service
from app.translation_engine import TranslationUnavailableError


def _run(coro):
    return asyncio.run(coro)


def test_translate_with_fallback_posts_context_request(monkeypatch):
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content.decode()))
        return httpx.Response(200, json={"translation": "河岸", "is_fallback": True})

    monkeypatch.setattr(
        translation_engine_service.settings_service,
        "load",
        lambda: {"ai_provider": "deepseek", "use_free_translation_fallback": True},
    )
    monkeypatch.setattr(
        translation_engine_service,
        "_transport",
        httpx.MockTransport(handler),
    )

    result = _run(
        translation_engine_service.translate_in_context_with_fallback(
            "bank",
            "The boat reached the bank.",
        )
    )

    assert result.translation == "河岸"
    assert result.is_fallback is True
    assert calls == [
        {
            "word": "bank",
            "sentence": "The boat reached the bank.",
            "source_language": "en",
            "target_language": "zh-CN",
            "ai_provider": "deepseek",
            "use_fallback": True,
        }
    ]


def test_batch_translate_article_posts_batch_request(monkeypatch):
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content.decode()))
        return httpx.Response(200, json={"translations": {"0_1": "银行"}})

    monkeypatch.setattr(
        translation_engine_service.settings_service,
        "load",
        lambda: {"ai_provider": "openai", "use_free_translation_fallback": False},
    )
    monkeypatch.setattr(
        translation_engine_service,
        "_transport",
        httpx.MockTransport(handler),
    )

    result = _run(
        translation_engine_service.batch_translate_article(
            "The bank approved the loan.",
            [(0, 1, "bank")],
            [{"index": 0, "text": "The bank approved the loan."}],
        )
    )

    assert result == {"0_1": "银行"}
    assert calls == [
        {
            "article_text": "The bank approved the loan.",
            "word_entries": [[0, 1, "bank"]],
            "sentences": [{"index": 0, "text": "The bank approved the loan."}],
            "ai_provider": "openai",
        }
    ]


def test_service_503_maps_to_translation_unavailable(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "provider down"})

    monkeypatch.setattr(
        translation_engine_service,
        "_transport",
        httpx.MockTransport(handler),
    )

    with pytest.raises(TranslationUnavailableError, match="provider down"):
        _run(translation_engine_service.translate_in_context("bank", "by the bank"))
