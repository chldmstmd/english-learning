from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.annotation import ArticleAnnotation
from app.models.article import Article


def _key(sentence_index: int, word_index: int) -> str:
    return f"{sentence_index}-{word_index}"


async def get_article_annotations(
    db: AsyncSession, article_id: str, user_id: str
) -> dict[str, dict]:
    """Return {"{sidx}-{widx}": annotation_dict} for a given article, skipping stale ones."""
    rows = list(await db.scalars(
        select(ArticleAnnotation).where(
            ArticleAnnotation.article_id == article_id,
            ArticleAnnotation.user_id == user_id,
        )
    ))
    return {
        _key(ann.sentence_index, ann.word_index): {
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
    word: str,
    sentence_index: int,
    word_index: int,
    translation: str | None = None,
    source_sentence: str | None = None,
    is_fallback: bool = False,
    gen_status: str = "done",
) -> ArticleAnnotation:
    existing = await db.scalar(
        select(ArticleAnnotation).where(
            ArticleAnnotation.article_id == article_id,
            ArticleAnnotation.user_id == user_id,
            ArticleAnnotation.sentence_index == sentence_index,
            ArticleAnnotation.word_index == word_index,
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

    ann = ArticleAnnotation(
        article_id=article_id,
        user_id=user_id,
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


async def get_word_click_locations(
    db: AsyncSession, user_id: str, word: str, limit: int = 3
) -> list[dict]:
    """Recent positions where the user clicked this lemma, newest first."""
    rows = list(await db.execute(
        select(ArticleAnnotation, Article.title, Article.is_library)
        .join(Article, Article.id == ArticleAnnotation.article_id)
        .where(
            ArticleAnnotation.user_id == user_id,
            ArticleAnnotation.word == word,
        )
        .order_by(ArticleAnnotation.created_at.desc())
        .limit(limit)
    ))
    return [
        {
            "article_id": ann.article_id,
            "article_title": title,
            "is_library": bool(is_library),
            "sentence_index": ann.sentence_index,
            "source_sentence": ann.source_sentence,
            "is_stale": ann.is_stale,
        }
        for ann, title, is_library in rows
    ]


async def revalidate_article_annotations(
    db: AsyncSession, article_id: str, tokens: list[dict]
) -> None:
    """
    After an article is re-tokenized, mark annotations stale when the token now
    sitting at (sentence_index, word_index) no longer has the same lemma.
    Sweeps ALL users' annotations for this article. Caller commits.
    """
    # Map (sentence_index, word_index) -> lemma from the new tokens.
    pos_lemma = {
        (t["sentence_index"], t["index"]): t.get("lemma")
        for t in tokens
        if t.get("is_alpha")
    }
    rows = list(await db.scalars(
        select(ArticleAnnotation).where(ArticleAnnotation.article_id == article_id)
    ))
    for ann in rows:
        current = pos_lemma.get((ann.sentence_index, ann.word_index))
        ann.is_stale = current != ann.word


async def delete_word_annotations(
    db: AsyncSession, user_id: str, word: str
) -> None:
    """Delete all position annotations for a user's lemma across every article.

    Used when a word is removed from vocabulary ("uncollect") so no stale
    translation lingers in the reader. Caller commits.
    """
    rows = list(await db.scalars(
        select(ArticleAnnotation).where(
            ArticleAnnotation.user_id == user_id,
            ArticleAnnotation.word == word,
        )
    ))
    for ann in rows:
        await db.delete(ann)
