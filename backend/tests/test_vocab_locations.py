"""vocab detail exposes recent click locations for a lemma."""
import asyncio
from uuid import uuid4

from sqlalchemy import delete
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


def test_locations_returns_recent_three():
    uid = str(uuid4())   # user_id / article_id are VARCHAR(36) — no prefix
    aid = str(uuid4())

    async def scenario(session_factory):
        try:
            async with session_factory() as db:
                db.add(Article(
                    id=aid, user_id=uid, title="My Article", raw_text="x",
                    tokens=[], sentences=[], word_count=0, is_library=False,
                ))
                for i in range(4):
                    await annotation_service.upsert_annotation(
                        db, aid, uid, "bank", sentence_index=i, word_index=i,
                        translation="银行", source_sentence=f"sentence {i}")
                await db.commit()

            async with session_factory() as db:
                locs = await annotation_service.get_word_click_locations(db, uid, "bank", limit=3)
            assert len(locs) == 3
            assert locs[0]["article_title"] == "My Article"
            assert locs[0]["is_library"] is False
            assert "sentence_index" in locs[0]
        finally:
            async with session_factory() as db:
                await db.execute(delete(ArticleAnnotation).where(ArticleAnnotation.user_id == uid))
                await db.execute(delete(Article).where(Article.id == aid))
                await db.commit()

    _run(scenario)
