from __future__ import annotations

from fastapi import FastAPI, HTTPException

from translation_engine import (
    TranslationProviderError,
    TranslationResponseError,
    TranslationUnavailableError,
)

from .engine_factory import (
    VALID_PROVIDERS,
    create_translation_engine,
    normalize_provider_name,
)
from .schemas import (
    BatchTranslationRequest,
    BatchTranslationResponse,
    ContextTranslationRequest,
    ContextTranslationResponse,
)

app = FastAPI(title="Translation Service")


def _provider_runtime_settings(provider_name: str, **extra: object) -> dict[str, object]:
    normalized = normalize_provider_name(provider_name)
    if normalized not in VALID_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown translation provider: {provider_name}")
    return {"ai_provider": normalized, **extra}


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, TranslationProviderError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, TranslationResponseError):
        return HTTPException(status_code=502, detail=str(exc))
    if isinstance(exc, TranslationUnavailableError):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=503, detail="Translation provider unavailable")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/translate/context", response_model=ContextTranslationResponse)
async def translate_context(body: ContextTranslationRequest) -> ContextTranslationResponse:
    runtime_settings = _provider_runtime_settings(
        body.ai_provider,
        use_free_translation_fallback=body.use_fallback,
    )
    engine = create_translation_engine(runtime_settings)
    try:
        if body.use_fallback:
            result = await engine.translate_in_context_with_fallback(
                body.word,
                body.sentence,
                source_language=body.source_language,
                target_language=body.target_language,
            )
            return ContextTranslationResponse(
                translation=result.translation,
                is_fallback=result.is_fallback,
            )

        translation = await engine.translate_in_context(
            body.word,
            body.sentence,
            source_language=body.source_language,
            target_language=body.target_language,
        )
        return ContextTranslationResponse(translation=translation, is_fallback=False)
    except Exception as exc:
        raise _map_error(exc) from exc


@app.post("/v1/translate/batch", response_model=BatchTranslationResponse)
async def translate_batch(body: BatchTranslationRequest) -> BatchTranslationResponse:
    runtime_settings = _provider_runtime_settings(body.ai_provider)
    engine = create_translation_engine(runtime_settings)
    try:
        translations = await engine.batch_translate_article(
            body.article_text,
            body.word_entries,
            [sentence.model_dump() for sentence in body.sentences],
        )
    except Exception as exc:
        raise _map_error(exc) from exc
    return BatchTranslationResponse(translations=translations)
