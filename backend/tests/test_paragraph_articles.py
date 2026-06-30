from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base
from app.models.article import Article
from app.models.user import User
from app.routers import articles as articles_router
from app.routers import translate as translate_router
from app.schemas.article import ArticleCreateRequest, ArticleUpdateRequest
from app.schemas.translate import TranslateRequest
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


async def _cleanup(session_factory, user_id: str) -> None:
    from app.models.paragraph import ArticleParagraph, ParagraphTranslation

    async with session_factory() as db:
        article_ids = list(await db.scalars(select(Article.id).where(Article.user_id == user_id)))
        if article_ids:
            version_ids = list(await db.scalars(
                select(ArticleParagraph.paragraph_version_id)
                .where(ArticleParagraph.article_id.in_(article_ids))
            ))
            if version_ids:
                await db.execute(
                    delete(ParagraphTranslation)
                    .where(ParagraphTranslation.paragraph_version_id.in_(version_ids))
                )
        await db.execute(delete(Article).where(Article.user_id == user_id))
        await db.commit()


def test_create_article_stores_ordered_paragraph_versions():
    from app.models.paragraph import ArticleParagraph, ParagraphVersion

    user_id = str(uuid4())
    user = User(id=user_id, email="paragraph-create@example.com", hashed_password="x")

    async def scenario(session_factory):
        try:
            async with session_factory() as db:
                article = await articles_router.create_article(
                    ArticleCreateRequest(
                        title="Paragraph create",
                        raw_text="Alpha beta.\n\nGamma delta.",
                    ),
                    db=db,
                    current_user=user,
                )

            async with session_factory() as db:
                rows = (
                    await db.execute(
                        select(ArticleParagraph, ParagraphVersion)
                        .join(ParagraphVersion, ArticleParagraph.paragraph_version_id == ParagraphVersion.id)
                        .where(ArticleParagraph.article_id == article.id)
                        .order_by(ArticleParagraph.position)
                    )
                ).all()

            assert article.word_count == 4
            assert [link.position for link, _ in rows] == [0, 1]
            assert [version.raw_text for _, version in rows] == ["Alpha beta.", "Gamma delta."]
            assert [version.word_count for _, version in rows] == [2, 2]
        finally:
            await _cleanup(session_factory, user_id)

    _run(scenario)


def test_edit_preserves_translations_for_unchanged_paragraphs():
    from app.models.paragraph import ArticleParagraph, ParagraphTranslation, ParagraphVersion

    user_id = str(uuid4())
    user = User(id=user_id, email="paragraph-edit@example.com", hashed_password="x")

    async def scenario(session_factory):
        try:
            async with session_factory() as db:
                article = await articles_router.create_article(
                    ArticleCreateRequest(
                        title="Paragraph edit",
                        raw_text="Keep bank.\n\nChange cat.",
                    ),
                    db=db,
                    current_user=user,
                )

            async with session_factory() as db:
                first_link = await db.scalar(
                    select(ArticleParagraph)
                    .where(ArticleParagraph.article_id == article.id)
                    .order_by(ArticleParagraph.position)
                    .limit(1)
                )
                assert first_link is not None
                original_first_link_id = first_link.id
                original_first_version_id = first_link.paragraph_version_id
                await db.execute(
                    delete(ParagraphTranslation)
                    .where(ParagraphTranslation.paragraph_version_id == original_first_version_id)
                )
                db.add_all(
                    [
                        ParagraphTranslation(
                            paragraph_version_id=original_first_version_id,
                            sentence_index=0,
                            word_index=0,
                            word="Keep",
                            lemma="keep",
                            translation="保留",
                        ),
                        ParagraphTranslation(
                            paragraph_version_id=original_first_version_id,
                            sentence_index=0,
                            word_index=1,
                            word="bank",
                            lemma="bank",
                            translation="银行",
                        ),
                    ]
                )
                article_row = await db.get(Article, article.id)
                assert article_row is not None
                article_row.translation_status = "done"
                article_row.translation_total_words = 4
                article_row.translation_processed_words = 4
                article_row.translation_total_chunks = 2
                article_row.translation_completed_chunks = 2
                await db.commit()

            async with session_factory() as db:
                updated = await articles_router.update_article(
                    article.id,
                    ArticleUpdateRequest(
                        title="Paragraph edit",
                        raw_text="Keep bank.\n\nChanged dog.",
                    ),
                    db=db,
                    current_user=user,
                )

            async with session_factory() as db:
                rows = (
                    await db.execute(
                        select(ArticleParagraph, ParagraphVersion)
                        .join(ParagraphVersion, ArticleParagraph.paragraph_version_id == ParagraphVersion.id)
                        .where(ArticleParagraph.article_id == article.id)
                        .order_by(ArticleParagraph.position)
                    )
                ).all()
                preserved_count = await db.scalar(
                    select(func.count())
                    .select_from(ParagraphTranslation)
                    .where(ParagraphTranslation.paragraph_version_id == original_first_version_id)
                )
                changed_count = await db.scalar(
                    select(func.count())
                    .select_from(ParagraphTranslation)
                    .where(ParagraphTranslation.paragraph_version_id == rows[1][0].paragraph_version_id)
                )

            assert updated.translation_status == "stale"
            assert updated.translation_progress.processed_words == 2
            assert updated.translation_progress.total_words == 4
            assert rows[0][0].id == original_first_link_id
            assert rows[0][0].paragraph_version_id == original_first_version_id
            assert rows[0][1].raw_text == "Keep bank."
            assert rows[1][1].raw_text == "Changed dog."
            assert preserved_count == 2
            assert changed_count == 0
        finally:
            await _cleanup(session_factory, user_id)

    _run(scenario)


def test_translate_word_uses_paragraph_version_cache(monkeypatch):
    from app.models.paragraph import ArticleParagraph, ParagraphTranslation

    user_id = str(uuid4())
    user = User(id=user_id, email="paragraph-cache@example.com", hashed_password="x")

    async def fail_if_called(word: str, sentence: str):
        raise AssertionError("AI translation should not be called on paragraph cache hit")

    monkeypatch.setattr(translate_router, "_get_translation_with_fallback", fail_if_called)

    async def scenario(session_factory):
        try:
            async with session_factory() as db:
                article = await articles_router.create_article(
                    ArticleCreateRequest(
                        title="Paragraph cache",
                        raw_text="The bank.",
                    ),
                    db=db,
                    current_user=user,
                )

            async with session_factory() as db:
                link = await db.scalar(
                    select(ArticleParagraph).where(ArticleParagraph.article_id == article.id)
                )
                assert link is not None
                await db.execute(
                    delete(ParagraphTranslation)
                    .where(ParagraphTranslation.paragraph_version_id == link.paragraph_version_id)
                )
                db.add(
                    ParagraphTranslation(
                        paragraph_version_id=link.paragraph_version_id,
                        sentence_index=0,
                        word_index=1,
                        word="bank",
                        lemma="bank",
                        translation="河岸",
                    )
                )
                await db.commit()

            async with session_factory() as db:
                response = await translate_router.translate_word(
                    TranslateRequest(
                        word="bank",
                        lemma="bank",
                        sentence="The bank.",
                        article_id=article.id,
                        article_paragraph_id=link.id,
                        sentence_index=0,
                        word_index=1,
                    ),
                    db=db,
                    current_user=user,
                )

            assert response.translation == "河岸"
            assert response.is_fallback is False
        finally:
            await _cleanup(session_factory, user_id)

    _run(scenario)
