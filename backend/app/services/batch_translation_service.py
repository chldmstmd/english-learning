import asyncio
import logging

from sqlalchemy import select, update, func, delete as sa_delete
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import AsyncSessionLocal
from app.models.article import Article
from app.models.article_translation import ArticleTranslation
from app.services import ai_service

logger = logging.getLogger(__name__)

# The event loop only keeps a weak reference to tasks, so a fire-and-forget
# task can be garbage-collected mid-flight. Hold a strong reference until it
# finishes so the translation always runs to completion (and reaches its own
# failure handling on error). See https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task
_background_tasks: set[asyncio.Task] = set()


def spawn_translation(article_id: str) -> None:
    """Start a batch translation as a tracked background task."""
    task = asyncio.create_task(translate_article(article_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _set_status(db, article_id: str, status: str) -> None:
    await db.execute(
        update(Article).where(Article.id == article_id).values(translation_status=status)
    )
    await db.commit()


async def recover_stuck_translations(db) -> int:
    """Reset articles stranded in `processing` to `failed`.

    Batch translation runs as a fire-and-forget background task that flips the
    article to `processing` before calling the AI. If the process dies (or the
    task is GC'd) mid-flight, the `except` branch that sets `failed` never runs
    and the article is deadlocked: it stays `processing` forever and the trigger
    endpoints refuse to re-run a `processing` article.

    Any `processing` row seen at process startup can only be such a corpse — a
    live task only exists within a running process — so we reset them to
    `failed`, which the UI exposes a retry action for. Returns how many rows
    were recovered.
    """
    result = await db.execute(
        update(Article)
        .where(Article.translation_status == "processing")
        .values(translation_status="failed")
    )
    await db.commit()
    count = result.rowcount or 0
    if count:
        logger.warning("Recovered %d translation(s) stuck in 'processing' -> 'failed'", count)
    return count


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

        if article.translation_status in ("processing", "done"):
            return

        await _set_status(db, article_id, "processing")

        try:
            # Build word entries: [(sentence_index, word_index, text, lemma)]
            word_entries = [
                (token["sentence_index"], token["index"], token["text"], token["lemma"])
                for token in article.tokens
                if token["is_alpha"]
            ]

            if not word_entries:
                await _set_status(db, article_id, "done")
                return

            # Delete stale translations before re-translating
            await db.execute(sa_delete(ArticleTranslation).where(ArticleTranslation.article_id == article_id))
            await db.commit()

            # Call AI with sentence-grouped context
            ai_entries = [(si, wi, text) for si, wi, text, _ in word_entries]
            translations = await ai_service.batch_translate_article(
                article.raw_text, ai_entries, article.sentences
            )

            # Build DB rows — key format is "si_wi"
            values = []
            for si, wi, word, lemma in word_entries:
                key = f"{si}_{wi}"
                translation = translations.get(key, "")
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
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_article_word_position",
                    set_={"translation": pg_insert(ArticleTranslation).excluded.translation},
                )
                await db.execute(stmt)
                await db.commit()

            await _set_status(db, article_id, "done")
            logger.info("Batch translation complete for article %s (%d words)", article_id, len(values))

        except Exception as exc:
            logger.error("Batch translation failed for article %s: %s", article_id, exc)
            await db.rollback()
            await _set_status(db, article_id, "failed")
