from __future__ import annotations

import asyncio
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base
from app.models.article import Article
from app.models.paragraph import ArticleParagraph, ParagraphTranslation
from app.services import batch_translation_service
from app.services import paragraph_service
from app.services.schema_service import ensure_runtime_schema


def _run(coro_fn):
    async def wrapper():
        engine = create_async_engine(settings.database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                await ensure_runtime_schema(conn)
            await coro_fn(session_factory)
        finally:
            await engine.dispose()

    asyncio.run(wrapper())


def _token(text: str, index: int, sentence_index: int) -> dict:
    return {
        "text": text,
        "lemma": text.lower(),
        "index": index,
        "sentence_index": sentence_index,
        "is_punct": False,
        "is_alpha": True,
        "pos": "NN",
        "ws": " ",
    }


async def _seed_article(session_factory, article: Article) -> None:
    async with session_factory() as db:
        db.add(article)
        await db.flush()
        await paragraph_service.replace_article_paragraphs(db, article, article.raw_text)
        version_ids = list(await db.scalars(
            select(ArticleParagraph.paragraph_version_id)
            .where(ArticleParagraph.article_id == article.id)
        ))
        if version_ids:
            await db.execute(
                delete(ParagraphTranslation)
                .where(ParagraphTranslation.paragraph_version_id.in_(version_ids))
            )
        await db.commit()


async def _cleanup(session_factory, article_id: str) -> None:
    async with session_factory() as db:
        version_ids = list(await db.scalars(
            select(ArticleParagraph.paragraph_version_id)
            .where(ArticleParagraph.article_id == article_id)
        ))
        if version_ids:
            await db.execute(
                delete(ParagraphTranslation)
                .where(ParagraphTranslation.paragraph_version_id.in_(version_ids))
            )
        await db.execute(delete(Article).where(Article.id == article_id))
        await db.commit()


async def _version_ids_for_article(db, article_id: str) -> list[str]:
    return list(await db.scalars(
        select(ArticleParagraph.paragraph_version_id)
        .where(ArticleParagraph.article_id == article_id)
    ))


def test_chunked_pretranslation_resumes_after_failed_chunk(monkeypatch):
    article_id = str(uuid4())
    article = Article(
        id=article_id,
        user_id=str(uuid4()),
        title="chunk-test",
        raw_text="Alpha beta. Gamma delta.",
        tokens=[
            _token("Alpha", 0, 0),
            _token("beta", 1, 0),
            _token("Gamma", 0, 1),
            _token("delta", 1, 1),
        ],
        sentences=[
            {"index": 0, "text": "Alpha beta."},
            {"index": 1, "text": "Gamma delta."},
        ],
        word_count=4,
        translation_status="untranslated",
    )
    calls: list[list[tuple[int, int, str]]] = []

    async def fail_on_second_chunk(article_text, word_entries, sentences):
        calls.append(word_entries)
        if len(calls) == 2:
            raise RuntimeError("provider interrupted")
        return {f"{si}_{wi}": f"{word}-zh" for si, wi, word in word_entries}

    async def translate_remaining(article_text, word_entries, sentences):
        calls.append(word_entries)
        return {f"{si}_{wi}": f"{word}-zh" for si, wi, word in word_entries}

    async def scenario(session_factory):
        original_limit = batch_translation_service.TRANSLATION_CHUNK_WORD_LIMIT
        monkeypatch.setattr(batch_translation_service, "AsyncSessionLocal", session_factory)
        monkeypatch.setattr(batch_translation_service, "TRANSLATION_CHUNK_WORD_LIMIT", 2)
        monkeypatch.setattr(
            batch_translation_service,
            "batch_translate_article",
            fail_on_second_chunk,
        )
        await _seed_article(session_factory, article)
        try:
            await batch_translation_service.translate_article(article_id)
            async with session_factory() as db:
                version_ids = await _version_ids_for_article(db, article_id)
                status, processed, completed = (
                    await db.execute(
                        select(
                            Article.translation_status,
                            Article.translation_processed_words,
                            Article.translation_completed_chunks,
                        ).where(Article.id == article_id)
                    )
                ).one()
                cached_count = await db.scalar(
                    select(func.count()).select_from(ParagraphTranslation)
                    .where(ParagraphTranslation.paragraph_version_id.in_(version_ids))
                )
            assert status == "failed"
            assert processed == 2
            assert completed == 1
            assert cached_count == 2

            monkeypatch.setattr(
                batch_translation_service,
                "batch_translate_article",
                translate_remaining,
            )
            await batch_translation_service.translate_article(article_id)
            async with session_factory() as db:
                version_ids = await _version_ids_for_article(db, article_id)
                status, processed, completed, total_chunks = (
                    await db.execute(
                        select(
                            Article.translation_status,
                            Article.translation_processed_words,
                            Article.translation_completed_chunks,
                            Article.translation_total_chunks,
                        ).where(Article.id == article_id)
                    )
                ).one()
                cached_count = await db.scalar(
                    select(func.count()).select_from(ParagraphTranslation)
                    .where(ParagraphTranslation.paragraph_version_id.in_(version_ids))
                )
            assert status == "done"
            assert processed == 4
            assert completed == total_chunks == 2
            assert cached_count == 4
            assert len(calls) == 3
        finally:
            batch_translation_service.TRANSLATION_CHUNK_WORD_LIMIT = original_limit
            await _cleanup(session_factory, article_id)

    _run(scenario)
