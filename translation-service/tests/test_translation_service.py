from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from translation_engine.engine import TranslationEngine
from translation_service import main as service_main
from translation_service import engine_factory


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
        self.calls.append(
            {
                "word": word,
                "source_language": source_language,
                "target_language": target_language,
            }
        )
        return self.translation


def _override_engine(monkeypatch, engine: TranslationEngine) -> None:
    monkeypatch.setattr(service_main, "create_translation_engine", lambda runtime_settings: engine)


def test_context_translation_without_fallback_calls_provider_only(monkeypatch):
    provider = FakeProvider('{"translation": "银行"}')
    engine = TranslationEngine(
        providers={"deepseek": provider},
        fallback_translator=FakeFallback("fallback"),
        runtime_settings_loader=lambda: {},
    )
    _override_engine(monkeypatch, engine)
    client = TestClient(service_main.app)

    response = client.post(
        "/v1/translate/context",
        json={
            "word": "bank",
            "sentence": "The bank approved the loan.",
            "source_language": "en",
            "target_language": "zh-CN",
            "ai_provider": "deepseek",
            "use_fallback": False,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"translation": "银行", "is_fallback": False}
    assert provider.calls[0]["request_kind"] == "single"


def test_context_translation_with_fallback_returns_fallback_result(monkeypatch):
    provider = FakeProvider(error=RuntimeError("provider down"))
    fallback = FakeFallback("河岸")
    engine = TranslationEngine(
        providers={"deepseek": provider},
        fallback_translator=fallback,
        runtime_settings_loader=lambda: {},
    )
    _override_engine(monkeypatch, engine)
    client = TestClient(service_main.app)

    response = client.post(
        "/v1/translate/context",
        json={
            "word": "bank",
            "sentence": "The boat reached the bank.",
            "ai_provider": "deepseek",
            "use_fallback": True,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"translation": "河岸", "is_fallback": True}
    assert fallback.calls == [
        {
            "word": "bank",
            "source_language": "en",
            "target_language": "zh-CN",
        }
    ]


def test_batch_translation_returns_translation_map(monkeypatch):
    provider = FakeProvider('{"0_1": "银行", "0_2": "批准"}')
    engine = TranslationEngine(
        providers={"deepseek": provider},
        runtime_settings_loader=lambda: {},
    )
    _override_engine(monkeypatch, engine)
    client = TestClient(service_main.app)

    response = client.post(
        "/v1/translate/batch",
        json={
            "article_text": "The bank approved the loan.",
            "word_entries": [[0, 1, "bank"], [0, 2, "approved"]],
            "sentences": [{"index": 0, "text": "The bank approved the loan."}],
            "ai_provider": "deepseek",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"translations": {"0_1": "银行", "0_2": "批准"}}
    assert provider.calls[0]["request_kind"] == "batch"


def test_mock_mode_context_translation_does_not_require_ai_provider(monkeypatch):
    monkeypatch.setattr(
        engine_factory,
        "settings",
        SimpleNamespace(translation_engine_mock=True),
    )
    client = TestClient(service_main.app)

    response = client.post(
        "/v1/translate/context",
        json={
            "word": "bank",
            "sentence": "The boat reached the bank.",
            "ai_provider": "deepseek",
            "use_fallback": False,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"translation": "mock: bank", "is_fallback": False}


def test_mock_mode_batch_translation_returns_each_word(monkeypatch):
    monkeypatch.setattr(
        engine_factory,
        "settings",
        SimpleNamespace(translation_engine_mock=True),
    )
    client = TestClient(service_main.app)

    response = client.post(
        "/v1/translate/batch",
        json={
            "article_text": "The bank approved the loan.",
            "word_entries": [[0, 1, "bank"], [0, 2, "approved"]],
            "sentences": [{"index": 0, "text": "The bank approved the loan."}],
            "ai_provider": "deepseek",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "translations": {
            "0_1": "mock: bank",
            "0_2": "mock: approved",
        }
    }
