from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.article import Article
from app.models.article_translation import ArticleTranslation
from app.models.user import User
from app.schemas.translate import TranslateRequest, TranslateResponse
from app.services import annotation_service
from app.services.translation_engine_service import translate_in_context_with_fallback
from app.translation_engine import TranslationUnavailableError

router = APIRouter(tags=["translate"])


async def _get_translation_with_fallback(word: str, sentence: str) -> tuple[str, bool]:
    try:
        result = await translate_in_context_with_fallback(word, sentence)
        return result.translation, result.is_fallback
    except TranslationUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/translate-word", response_model=TranslateResponse)
async def translate_word(
    body: TranslateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    article = await db.scalar(
        select(Article).where(
            Article.id == body.article_id,
            Article.user_id == current_user.id,
        )
    )
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

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
    )
