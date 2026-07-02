from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import httpx

from app.config import settings
from app.services import settings_service


class TranslationClientError(RuntimeError):
    pass


class TranslationProviderError(TranslationClientError):
    pass


class TranslationResponseError(TranslationClientError):
    pass


class TranslationUnavailableError(TranslationClientError):
    pass


@dataclass(frozen=True)
class TranslationResult:
    translation: str
    is_fallback: bool = False

_transport: httpx.AsyncBaseTransport | None = None


def _runtime_settings() -> dict:
    return settings_service.load()


def _service_url() -> str:
    return settings.translation_service_url.rstrip("/")


def _detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text or "Translation service error"
    detail = body.get("detail") if isinstance(body, dict) else None
    return str(detail or "Translation service error")


async def _post(path: str, payload: dict, timeout: float) -> dict:
    try:
        async with httpx.AsyncClient(
            base_url=_service_url(),
            timeout=timeout,
            transport=_transport,
        ) as client:
            response = await client.post(path, json=payload)
    except httpx.TimeoutException as exc:
        raise TranslationUnavailableError("Translation service timed out") from exc
    except httpx.HTTPError as exc:
        raise TranslationUnavailableError("Translation service unavailable") from exc

    if response.status_code == 400:
        raise TranslationProviderError(_detail(response))
    if response.status_code == 502:
        raise TranslationResponseError(_detail(response))
    if response.status_code == 503:
        raise TranslationUnavailableError(_detail(response))
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise TranslationUnavailableError(_detail(response)) from exc
    return response.json()


async def translate_in_context(
    word: str,
    sentence: str,
    source_language: str = "en",
    target_language: str = "zh-CN",
) -> str:
    runtime_settings = _runtime_settings()
    payload = {
        "word": word,
        "sentence": sentence,
        "source_language": source_language,
        "target_language": target_language,
        "ai_provider": runtime_settings.get("ai_provider", "deepseek"),
        "use_fallback": False,
    }
    data = await _post("/v1/translate/context", payload, timeout=10.0)
    translation = data.get("translation")
    if not isinstance(translation, str):
        raise TranslationResponseError("Translation service response is missing translation")
    return translation


async def translate_in_context_with_fallback(
    word: str,
    sentence: str,
    source_language: str = "en",
    target_language: str = "zh-CN",
    *,
    use_fallback: bool | None = None,
) -> TranslationResult:
    runtime_settings = _runtime_settings()
    fallback_enabled = (
        bool(runtime_settings.get("use_free_translation_fallback", True))
        if use_fallback is None
        else use_fallback
    )
    payload = {
        "word": word,
        "sentence": sentence,
        "source_language": source_language,
        "target_language": target_language,
        "ai_provider": runtime_settings.get("ai_provider", "deepseek"),
        "use_fallback": fallback_enabled,
    }
    data = await _post("/v1/translate/context", payload, timeout=10.0)
    translation = data.get("translation")
    if not isinstance(translation, str):
        raise TranslationResponseError("Translation service response is missing translation")
    return TranslationResult(
        translation=translation,
        is_fallback=bool(data.get("is_fallback", False)),
    )


async def batch_translate_article(
    article_text: str,
    word_entries: Sequence[tuple[int, int, str]],
    sentences: Sequence[dict],
) -> dict[str, str]:
    runtime_settings = _runtime_settings()
    payload = {
        "article_text": article_text,
        "word_entries": [list(entry) for entry in word_entries],
        "sentences": list(sentences),
        "ai_provider": runtime_settings.get("ai_provider", "deepseek"),
    }
    data = await _post("/v1/translate/batch", payload, timeout=190.0)
    translations = data.get("translations")
    if not isinstance(translations, dict):
        raise TranslationResponseError("Translation service response is missing translations")
    return {str(key): str(value) for key, value in translations.items()}
