from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.paragraph import ParagraphAnnotation


def _key(article_paragraph_id: str, sentence_index: int, word_index: int) -> str:
    return f"{article_paragraph_id}-{sentence_index}-{word_index}"


async def get_article_annotations(
    db: AsyncSession, article_id: str, user_id: str
) -> dict[str, dict]:
    """Return paragraph-position annotations for a given article, skipping stale ones."""
    rows = list(await db.scalars(
        select(ParagraphAnnotation).where(
            ParagraphAnnotation.article_id == article_id,
            ParagraphAnnotation.user_id == user_id,
        )
    ))
    return {
        _key(ann.article_paragraph_id, ann.sentence_index, ann.word_index): {
            "translation": ann.translation,
            "source_sentence": ann.source_sentence,
            "is_fallback": ann.is_fallback,
            "gen_status": ann.gen_status,
            "is_stale": ann.is_stale,
        }
        for ann in rows
        if not ann.is_stale
    }


async def upsert_annotation(
    db: AsyncSession,
    article_id: str,
    user_id: str,
    article_paragraph_id: str,
    word: str,
    sentence_index: int,
    word_index: int,
    translation: Optional[str] = None,
    source_sentence: Optional[str] = None,
    is_fallback: bool = False,
    gen_status: str = "done",
) -> ParagraphAnnotation:
    existing = await db.scalar(
        select(ParagraphAnnotation).where(
            ParagraphAnnotation.article_id == article_id,
            ParagraphAnnotation.user_id == user_id,
            ParagraphAnnotation.article_paragraph_id == article_paragraph_id,
            ParagraphAnnotation.sentence_index == sentence_index,
            ParagraphAnnotation.word_index == word_index,
        )
    )
    if existing:
        existing.word = word
        existing.translation = translation
        existing.source_sentence = source_sentence
        existing.is_fallback = is_fallback
        existing.gen_status = gen_status
        existing.is_stale = False
        await db.flush()
        return existing

    ann = ParagraphAnnotation(
        article_id=article_id,
        user_id=user_id,
        article_paragraph_id=article_paragraph_id,
        word=word,
        sentence_index=sentence_index,
        word_index=word_index,
        translation=translation,
        source_sentence=source_sentence,
        is_fallback=is_fallback,
        gen_status=gen_status,
        is_stale=False,
    )
    db.add(ann)
    await db.flush()
    return ann
