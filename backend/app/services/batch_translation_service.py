import logging

from sqlalchemy import select, update, func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import AsyncSessionLocal
from app.models.article import Article
from app.models.article_translation import ArticleTranslation
from app.services import ai_service

logger = logging.getLogger(__name__)


async def _set_status(db, article_id: str, status: str) -> None:
    await db.execute(
        update(Article).where(Article.id == article_id).values(translation_status=status)
    )
    await db.commit()


async def translate_article(article_id: str) -> None:
    """
    Batch-translate all alpha words in an article and store results.
    Intended to be called as a background task.
    """
    async with AsyncSessionLocal() as db:
        article = await db.scalar(
            select(Article).where(Article.id == article_id)
        )
        if not article:
            logger.error("Article %s not found for batch translation", article_id)
            return

        # Only skip if already processing or done
        if article.translation_status in ("processing", "done"):
            return

        await _set_status(db, article_id, "processing")

        try:
            # Build ordered word list from tokens (alpha only)
            word_entries = []  # [(sentence_index, word_index, text, lemma)]
            for token in article.tokens:
                if token["is_alpha"]:
                    word_entries.append((
                        token["sentence_index"],
                        token["index"],
                        token["text"],
                        token["lemma"],
                    ))

            if not word_entries:
                await _set_status(db, article_id, "done")
                return

            # Check if translations already exist (idempotency)
            existing_count = await db.scalar(
                select(func.count()).where(
                    ArticleTranslation.article_id == article_id
                )
            )
            if existing_count and existing_count >= len(word_entries):
                await _set_status(db, article_id, "done")
                return

            # Call AI with just the word texts (ordered)
            word_texts = [entry[2] for entry in word_entries]
            translations = await ai_service.batch_translate_article(
                article.raw_text, word_texts
            )

            # Zip translations with position info (indexing done here)
            values = []
            for (si, wi, word, lemma), translation in zip(word_entries, translations):
                values.append({
                    "article_id": article_id,
                    "sentence_index": si,
                    "word_index": wi,
                    "word": word,
                    "lemma": lemma,
                    "translation": translation,
                })

            if values:
                stmt = pg_insert(ArticleTranslation).values(values)
                stmt = stmt.on_conflict_do_nothing(
                    constraint="uq_article_word_position"
                )
                await db.execute(stmt)
                await db.commit()

            await _set_status(db, article_id, "done")
            logger.info("Batch translation complete for article %s (%d words)", article_id, len(values))

        except Exception as exc:
            logger.error("Batch translation failed for article %s: %s", article_id, exc)
            await db.rollback()
            await _set_status(db, article_id, "failed")
