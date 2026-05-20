from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.annotation import ArticleAnnotation


async def get_article_annotations(
    db: AsyncSession, article_id: str, user_id: str
) -> dict[str, dict]:
    """Return {word: annotation_dict} for a given article."""
    rows = list(await db.scalars(
        select(ArticleAnnotation).where(
            ArticleAnnotation.article_id == article_id,
            ArticleAnnotation.user_id == user_id,
        )
    ))
    return {
        ann.word: {
            "translation": ann.translation,
            "source_sentence": ann.source_sentence,
            "is_fallback": ann.is_fallback,
            "gen_status": ann.gen_status,
        }
        for ann in rows
    }


async def get_pending_annotations(
    db: AsyncSession, article_id: str, user_id: str
) -> list[ArticleAnnotation]:
    return list(await db.scalars(
        select(ArticleAnnotation).where(
            ArticleAnnotation.article_id == article_id,
            ArticleAnnotation.user_id == user_id,
            ArticleAnnotation.gen_status == "pending",
        )
    ))


async def upsert_annotation(
    db: AsyncSession,
    article_id: str,
    user_id: str,
    word: str,
    translation: str | None = None,
    source_sentence: str | None = None,
    is_fallback: bool = False,
    gen_status: str = "done",
) -> ArticleAnnotation:
    existing = await db.scalar(
        select(ArticleAnnotation).where(
            ArticleAnnotation.article_id == article_id,
            ArticleAnnotation.user_id == user_id,
            ArticleAnnotation.word == word,
        )
    )
    if existing:
        existing.translation = translation
        existing.source_sentence = source_sentence
        existing.is_fallback = is_fallback
        existing.gen_status = gen_status
        await db.flush()
        return existing

    ann = ArticleAnnotation(
        article_id=article_id,
        user_id=user_id,
        word=word,
        translation=translation,
        source_sentence=source_sentence,
        is_fallback=is_fallback,
        gen_status=gen_status,
    )
    db.add(ann)
    await db.flush()
    return ann


async def sync_word_to_user_articles_task(
    current_article_id: str,
    user_id: str,
    word: str,
) -> None:
    """
    Background task: for the user's OWN uploaded articles (not library) that contain
    this lemma, create a pending annotation so it gets translated on next open.
    Library articles use lazy sync instead (triggered on article open).
    """
    from app.database import AsyncSessionLocal
    from app.models.article import Article

    async with AsyncSessionLocal() as db:
        stmt = text(
            "SELECT id FROM articles "
            "WHERE user_id = :user_id "
            "AND is_library = false "
            "AND id != :current_article_id "
            "AND tokens @> :filter::jsonb"
        )
        result = await db.execute(stmt, {
            "user_id": user_id,
            "current_article_id": current_article_id,
            "filter": f'[{{"lemma": "{word}"}}]',
        })
        article_ids = [row[0] for row in result]

        for article_id in article_ids:
            existing = await db.scalar(
                select(ArticleAnnotation).where(
                    ArticleAnnotation.article_id == article_id,
                    ArticleAnnotation.user_id == user_id,
                    ArticleAnnotation.word == word,
                )
            )
            if not existing:
                db.add(ArticleAnnotation(
                    article_id=article_id,
                    user_id=user_id,
                    word=word,
                    gen_status="pending",
                ))

        await db.commit()


async def generate_pending_translations_task(article_id: str, user_id: str) -> None:
    """
    Background task: translate all pending annotations in an article.
    Runs after article load when cross-article synced words need translation.
    """
    from app.database import AsyncSessionLocal
    from app.models.article import Article
    from app.services import ai_service, dict_service
    from app.services.nlp_service import find_sentence_for_lemma
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        article = await db.scalar(select(Article).where(Article.id == article_id))
        if not article:
            return

        pending = await get_pending_annotations(db, article_id, user_id)
        from app.services import settings_service, free_translation_service

        use_fallback = settings_service.load().get("use_free_translation_fallback", True)

        for ann in pending:
            sentence = find_sentence_for_lemma(ann.word, article.tokens, article.sentences)
            try:
                translation = await ai_service.translate_in_context(ann.word, sentence)
                ann.translation = translation
                ann.source_sentence = sentence
                ann.is_fallback = False
                ann.gen_status = "done"
            except Exception:
                if use_fallback:
                    try:
                        translation = await free_translation_service.translate(ann.word)
                        ann.translation = translation
                        ann.source_sentence = sentence
                        ann.is_fallback = True
                        ann.gen_status = "done"
                    except Exception:
                        ann.gen_status = "failed"
                else:
                    ann.gen_status = "failed"

        await db.commit()
