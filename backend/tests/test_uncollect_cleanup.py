"""Deleting a vocab word also clears that lemma's position annotations."""
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


def test_delete_word_annotations_clears_all_positions():
    uid = str(uuid4())
    aid = str(uuid4())

    async def scenario(session_factory):
        try:
            async with session_factory() as db:
                db.add(Article(
                    id=aid, user_id=uid, title="t", raw_text="x",
                    tokens=[], sentences=[], word_count=0, is_library=False,
                ))
                await annotation_service.upsert_annotation(
                    db, aid, uid, "bank", sentence_index=0, word_index=1,
                    translation="银行", source_sentence="the bank")
                await annotation_service.upsert_annotation(
                    db, aid, uid, "bank", sentence_index=2, word_index=5,
                    translation="河岸", source_sentence="the river bank")
                # a different lemma must survive
                await annotation_service.upsert_annotation(
                    db, aid, uid, "river", sentence_index=2, word_index=3,
                    translation="河流", source_sentence="the river bank")
                await db.commit()

            async with session_factory() as db:
                await annotation_service.delete_word_annotations(db, uid, "bank")
                await db.commit()

            async with session_factory() as db:
                anns = await annotation_service.get_article_annotations(db, aid, uid)
            assert "0-1" not in anns
            assert "2-5" not in anns
            assert anns["2-3"]["translation"] == "河流"  # other lemma untouched
        finally:
            async with session_factory() as db:
                await db.execute(delete(ArticleAnnotation).where(ArticleAnnotation.user_id == uid))
                await db.execute(delete(Article).where(Article.id == aid))
                await db.commit()

    _run(scenario)
