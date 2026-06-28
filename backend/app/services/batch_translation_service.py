from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import AsyncSessionLocal
from app.models.article import Article
from app.models.article_translation import ArticleTranslation
from app.services.translation_engine_service import batch_translate_article

logger = logging.getLogger(__name__)
TRANSLATION_CHUNK_WORD_LIMIT = 120

# The event loop only keeps a weak reference to tasks, so a fire-and-forget
# task can be garbage-collected mid-flight. Hold a strong reference until it
# finishes so the translation always runs to completion (and reaches its own
# failure handling on error). See https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task
_background_tasks: set[asyncio.Task] = set()


@dataclass(frozen=True)
class TranslationChunk:
    index: int
    word_entries: list[tuple[int, int, str, str]]
    sentences: list[dict]

    @property
    def text(self) -> str:
        return "\n".join(sentence.get("text", "") for sentence in self.sentences)

    @property
    def keys(self) -> set[tuple[int, int]]:
        return {(sentence_index, word_index) for sentence_index, word_index, _, _ in self.word_entries}


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


def _build_translation_chunks(
    tokens: list[dict],
    sentences: list[dict],
    chunk_word_limit: int | None = None,
) -> list[TranslationChunk]:
    """Group translatable words into sentence-preserving chunks."""
    limit = chunk_word_limit or TRANSLATION_CHUNK_WORD_LIMIT
    words_by_sentence: dict[int, list[tuple[int, int, str, str]]] = defaultdict(list)
    for token in tokens:
        if token.get("is_alpha"):
            sentence_index = int(token["sentence_index"])
            words_by_sentence[sentence_index].append(
                (
                    sentence_index,
                    int(token["index"]),
                    str(token["text"]),
                    str(token["lemma"]),
                )
            )

    sentence_map = {int(sentence["index"]): sentence for sentence in sentences}
    chunks: list[TranslationChunk] = []
    current_words: list[tuple[int, int, str, str]] = []
    current_sentences: list[dict] = []

    def flush() -> None:
        nonlocal current_words, current_sentences
        if current_words:
            chunks.append(
                TranslationChunk(
                    index=len(chunks),
                    word_entries=current_words,
                    sentences=current_sentences,
                )
            )
            current_words = []
            current_sentences = []

    for sentence_index in sorted(words_by_sentence):
        entries = sorted(words_by_sentence[sentence_index], key=lambda entry: entry[1])
        if current_words and len(current_words) + len(entries) > limit:
            flush()
        current_words.extend(entries)
        current_sentences.append(
            sentence_map.get(sentence_index, {"index": sentence_index, "text": ""})
        )
        if len(current_words) >= limit:
            flush()

    flush()
    return chunks


def _all_chunk_keys(chunks: list[TranslationChunk]) -> set[tuple[int, int]]:
    return {key for chunk in chunks for key in chunk.keys}


def _count_completed_chunks(chunks: list[TranslationChunk], existing_keys: set[tuple[int, int]]) -> int:
    return sum(1 for chunk in chunks if chunk.keys <= existing_keys)


async def _load_existing_keys(db, article_id: str) -> set[tuple[int, int]]:
    rows = await db.execute(
        select(ArticleTranslation.sentence_index, ArticleTranslation.word_index)
        .where(ArticleTranslation.article_id == article_id)
    )
    return {(int(sentence_index), int(word_index)) for sentence_index, word_index in rows}


async def _save_progress(
    db,
    article_id: str,
    *,
    chunks: list[TranslationChunk],
    existing_keys: set[tuple[int, int]],
    status: str | None = None,
) -> dict:
    all_keys = _all_chunk_keys(chunks)
    processed_words = len(existing_keys & all_keys)
    total_words = len(all_keys)
    completed_chunks = _count_completed_chunks(chunks, existing_keys)
    values = {
        "translation_total_words": total_words,
        "translation_processed_words": processed_words,
        "translation_total_chunks": len(chunks),
        "translation_completed_chunks": completed_chunks,
    }
    if status is not None:
        values["translation_status"] = status
    await db.execute(update(Article).where(Article.id == article_id).values(**values))
    await db.commit()
    return {
        "total_words": total_words,
        "processed_words": processed_words,
        "total_chunks": len(chunks),
        "completed_chunks": completed_chunks,
        "percent": int(processed_words * 100 / total_words) if total_words else 0,
    }


async def prepare_translation_progress(db, article: Article) -> dict:
    chunks = _build_translation_chunks(article.tokens, article.sentences)
    existing_keys = await _load_existing_keys(db, article.id)
    return await _save_progress(
        db,
        article.id,
        chunks=chunks,
        existing_keys=existing_keys,
    )


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
            chunks = _build_translation_chunks(article.tokens, article.sentences)
            existing_keys = await _load_existing_keys(db, article_id)

            if not chunks:
                await _save_progress(
                    db,
                    article_id,
                    chunks=[],
                    existing_keys=set(),
                    status="done",
                )
                return

            await _save_progress(
                db,
                article_id,
                chunks=chunks,
                existing_keys=existing_keys,
                status="processing",
            )

            for chunk in chunks:
                missing_entries = [
                    entry for entry in chunk.word_entries if (entry[0], entry[1]) not in existing_keys
                ]
                if not missing_entries:
                    await _save_progress(
                        db,
                        article_id,
                        chunks=chunks,
                        existing_keys=existing_keys,
                        status="processing",
                    )
                    continue

                ai_entries = [(si, wi, text) for si, wi, text, _ in missing_entries]
                translations = await batch_translate_article(
                    chunk.text, ai_entries, chunk.sentences
                )

                values = []
                for si, wi, word, lemma in missing_entries:
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
                    existing_keys.update((si, wi) for si, wi, _, _ in missing_entries)

                await _save_progress(
                    db,
                    article_id,
                    chunks=chunks,
                    existing_keys=existing_keys,
                    status="processing",
                )

            existing_keys = await _load_existing_keys(db, article_id)
            await _save_progress(
                db,
                article_id,
                chunks=chunks,
                existing_keys=existing_keys,
                status="done",
            )
            logger.info("Batch translation complete for article %s (%d chunks)", article_id, len(chunks))

        except Exception as exc:
            logger.error("Batch translation failed for article %s: %s", article_id, exc)
            await db.rollback()
            try:
                chunks = _build_translation_chunks(article.tokens, article.sentences)
                existing_keys = await _load_existing_keys(db, article_id)
                await _save_progress(
                    db,
                    article_id,
                    chunks=chunks,
                    existing_keys=existing_keys,
                    status="failed",
                )
            except Exception:
                await _set_status(db, article_id, "failed")
