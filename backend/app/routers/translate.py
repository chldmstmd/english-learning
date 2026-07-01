from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.article import Article
from app.models.paragraph import ArticleParagraph, ParagraphTranslation
from app.models.user import User
from app.schemas.translate import TranslateRequest, TranslateResponse
from app.services import annotation_service
from app.services.translation_engine_service import (
    TranslationUnavailableError,
    translate_in_context_with_fallback,
)

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
    row = (
        await db.execute(
            select(ArticleParagraph, Article)
            .join(Article, ArticleParagraph.article_id == Article.id)
            .where(
                ArticleParagraph.id == body.article_paragraph_id,
                ArticleParagraph.article_id == body.article_id,
                Article.user_id == current_user.id,
            )
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Article paragraph not found")
    article_paragraph, _article = row

    cached = await db.scalar(
        select(ParagraphTranslation).where(
            ParagraphTranslation.paragraph_version_id == article_paragraph.paragraph_version_id,
            ParagraphTranslation.sentence_index == body.sentence_index,
            ParagraphTranslation.word_index == body.word_index,
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
        body.article_paragraph_id,
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
