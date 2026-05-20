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

        # Skip if already done
        if article.translation_status == "done":
            return

        await _set_status(db, article_id, "processing")

        try:
            # Build word list from tokens
            words = []
            token_lookup = {}
            for token in article.tokens:
                if token["is_alpha"]:
                    words.append({
                        "si": token["sentence_index"],
                        "wi": token["index"],
                        "w": token["text"],
                    })
                    token_lookup[(token["sentence_index"], token["index"])] = token["lemma"]

            if not words:
                await _set_status(db, article_id, "done")
                return

            # Check if translations already exist (idempotency)
            existing_count = await db.scalar(
                select(func.count()).where(
                    ArticleTranslation.article_id == article_id
                )
            )
            if existing_count and existing_count >= len(words):
                await _set_status(db, article_id, "done")
                return

            # Call AI
            translations = await ai_service.batch_translate_article(
                article.raw_text, words
            )

            # Build lookup from AI response
            trans_map = {(item["si"], item["wi"]): item["t"] for item in translations}

            # Upsert to DB (ON CONFLICT DO NOTHING)
            values = []
            for word_info in words:
                key = (word_info["si"], word_info["wi"])
                translation = trans_map.get(key, "")
                lemma = token_lookup.get(key, "")
                values.append({
                    "article_id": article_id,
                    "sentence_index": word_info["si"],
                    "word_index": word_info["wi"],
                    "word": word_info["w"],
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
