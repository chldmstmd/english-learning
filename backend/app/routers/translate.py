from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.article import Article
from app.models.article_translation import ArticleTranslation
from app.models.user import User
from app.schemas.translate import TranslateRequest, TranslateResponse
from app.services import ai_service, free_translation_service, settings_service, vocab_service, annotation_service

router = APIRouter(tags=["translate"])


async def _get_translation_with_fallback(word: str, sentence: str) -> tuple[str, bool]:
    try:
        translation = await ai_service.translate_in_context(word, sentence)
        return translation, False
    except Exception:
        if not settings_service.load().get("use_free_translation_fallback", True):
            raise HTTPException(status_code=503, detail="AI translation unavailable")
        try:
            translation = await free_translation_service.translate(word)
            return translation, True
        except Exception:
            raise HTTPException(status_code=503, detail="All translation services unavailable")


@router.post("/translate-word", response_model=TranslateResponse)
async def translate_word(
    body: TranslateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    article = await db.scalar(
        select(Article).where(
            Article.id == body.article_id,
            or_(Article.user_id == current_user.id, Article.is_library == True),  # noqa: E712
        )
    )
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    vocab = await vocab_service.upsert_word(
        db, current_user.id, body.lemma, source_sentence=body.sentence
    )

    # Dictionary-level Chinese meaning for the vocab list (word-level, context-free,
    # via free translation — not AI tokens). Best-effort, only when missing.
    if not vocab.context_translation:
        try:
            vocab.context_translation = await free_translation_service.translate(body.lemma)
        except Exception:
            pass  # leave null; vocab detail can fill it later

    # Check batch translation cache (per position)
    cached = await db.scalar(
        select(ArticleTranslation).where(
            ArticleTranslation.article_id == body.article_id,
            ArticleTranslation.sentence_index == body.sentence_index,
            ArticleTranslation.word_index == body.word_index,
        )
    )
    if cached and cached.translation:
        translation, is_fallback = cached.translation, False
    else:
        translation, is_fallback = await _get_translation_with_fallback(body.lemma, body.sentence)

    await annotation_service.upsert_annotation(
        db,
        body.article_id,
        current_user.id,
        body.lemma,
        sentence_index=body.sentence_index,
        word_index=body.word_index,
        translation=translation,
        source_sentence=body.sentence,
        is_fallback=is_fallback,
        gen_status="done",
    )

    await db.commit()

    return TranslateResponse(
        word=body.word,
        lemma=body.lemma,
        translation=translation,
        is_fallback=is_fallback,
        status=vocab.status,
    )
