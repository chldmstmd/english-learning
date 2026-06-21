"""
Position-based annotation tests. Annotations are keyed by token position
(sentence_index, word_index) instead of by lemma, so the same word at
different positions has independent translations.

Runs against the dockerized Postgres; each test seeds and cleans up its own
uniquely-id'd rows.
"""
import asyncio
from uuid import uuid4

from sqlalchemy import select, delete, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.config import settings
from app.models.annotation import ArticleAnnotation
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


def test_table_has_position_schema():
    async def scenario(session_factory):
        async with session_factory() as db:
            cols = await db.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'article_annotations'"
            ))
            names = {r[0] for r in cols}
            assert {"sentence_index", "word_index", "is_stale"} <= names

            uniq = await db.execute(text(
                "SELECT constraint_name FROM information_schema.table_constraints "
                "WHERE table_name = 'article_annotations' AND constraint_type = 'UNIQUE'"
            ))
            assert "uq_annotation_position" in {r[0] for r in uniq}

    _run(scenario)
