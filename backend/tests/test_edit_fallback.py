"""
Edit fallback: after an article is re-tokenized, position annotations whose
(sentence_index, word_index) no longer point at the same lemma are marked
is_stale so the reader stops showing a mis-placed translation.

Runs against the dockerized Postgres.
"""
import asyncio
from uuid import uuid4

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.config import settings
from app.models.annotation import ArticleAnnotation
from app.models.article import Article
from app.services import annotation_service


def _run(coro_fn):
    async def wrapper():
        engine = create_async_engine(settings.database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            await coro_fn(session_factory)
        finally:
            await engine.dispose()

    asyncio.run(wrapper())


def test_revalidate_marks_moved_word_stale_and_keeps_matching():
    uid = str(uuid4())   # user_id is VARCHAR(36) — no prefix
    aid = str(uuid4())

    async def scenario(session_factory):
        try:
            # article_id has an enforced FK to articles.id -> seed the article first
            async with session_factory() as db:
                db.add(Article(
                    id=aid, user_id=uid, title="t", raw_text="x",
                    tokens=[], sentences=[], word_count=0,
                ))
                await db.commit()
            async with session_factory() as db:
                # two clicks: bank@(0,1) and loan@(0,4)
                await annotation_service.upsert_annotation(
                    db, aid, uid, "bank", sentence_index=0, word_index=1, translation="银行")
                await annotation_service.upsert_annotation(
                    db, aid, uid, "loan", sentence_index=0, word_index=4, translation="贷款")
                await db.commit()

            # new tokens: position (0,1) is now "river" (moved), (0,4) is still "loan"
            new_tokens = [
                {"sentence_index": 0, "index": 1, "lemma": "river", "is_alpha": True},
                {"sentence_index": 0, "index": 4, "lemma": "loan", "is_alpha": True},
            ]
            async with session_factory() as db:
                await annotation_service.revalidate_article_annotations(db, aid, new_tokens)
                await db.commit()

            async with session_factory() as db:
                rows = {(a.sentence_index, a.word_index): a.is_stale for a in
                        await db.scalars(select(ArticleAnnotation).where(ArticleAnnotation.article_id == aid))}
            assert rows[(0, 1)] is True   # bank moved away -> stale
            assert rows[(0, 4)] is False  # loan still matches -> kept
        finally:
            async with session_factory() as db:
                await db.execute(delete(ArticleAnnotation).where(ArticleAnnotation.article_id == aid))
                await db.execute(delete(Article).where(Article.id == aid))
                await db.commit()

    _run(scenario)
