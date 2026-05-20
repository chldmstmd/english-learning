import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.article import Article
from app.models.article_translation import ArticleTranslation
from app.services import ai_service

logger = logging.getLogger(__name__)


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

        article.translation_status = "processing"
        await db.commit()

        try:
            # Build word list from tokens
            words = []
            for token in article.tokens:
                if token["is_alpha"]:
                    words.append({
                        "si": token["sentence_index"],
                        "wi": token["index"],
                        "w": token["text"],
                    })

            if not words:
                article.translation_status = "done"
                await db.commit()
                return

            # Call AI
            translations = await ai_service.batch_translate_article(
                article.raw_text, words
            )

            # Build lookup from AI response
            trans_map = {(item["si"], item["wi"]): item["t"] for item in translations}

            # Write to DB
            records = []
            for word_info in words:
                key = (word_info["si"], word_info["wi"])
                translation = trans_map.get(key, "")
                # Find lemma from tokens
                lemma = ""
                for token in article.tokens:
                    if token["index"] == word_info["wi"] and token["sentence_index"] == word_info["si"]:
                        lemma = token["lemma"]
                        break
                records.append(ArticleTranslation(
                    article_id=article_id,
                    sentence_index=word_info["si"],
                    word_index=word_info["wi"],
                    word=word_info["w"],
                    lemma=lemma,
                    translation=translation,
                ))

            db.add_all(records)
            article.translation_status = "done"
            await db.commit()
            logger.info("Batch translation complete for article %s (%d words)", article_id, len(records))

        except Exception as exc:
            logger.error("Batch translation failed for article %s: %s", article_id, exc)
            await db.rollback()
            # Re-fetch to update status
            async with AsyncSessionLocal() as db2:
                article = await db2.scalar(select(Article).where(Article.id == article_id))
                if article:
                    article.translation_status = "failed"
                    await db2.commit()
