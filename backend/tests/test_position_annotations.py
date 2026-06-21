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


async def _seed_article(session_factory, article_id, user_id):
    async with session_factory() as db:
        db.add(Article(
            id=article_id, user_id=user_id, title='t', raw_text='x',
            tokens=[], sentences=[], word_count=0,
        ))
        await db.commit()


async def _cleanup_anns(session_factory, user_id):
    async with session_factory() as db:
        await db.execute(delete(ArticleAnnotation).where(ArticleAnnotation.user_id == user_id))
        await db.execute(delete(Article).where(Article.user_id == user_id))
        await db.commit()


def test_same_lemma_different_positions_are_independent():
    uid = str(uuid4())
    aid = str(uuid4())

    async def scenario(session_factory):
        try:
            await _seed_article(session_factory, aid, uid)
            async with session_factory() as db:
                await annotation_service.upsert_annotation(
                    db, aid, uid, 'bank', sentence_index=0, word_index=3,
                    translation='河岸', source_sentence='by the bank of the river',
                )
                await annotation_service.upsert_annotation(
                    db, aid, uid, 'bank', sentence_index=1, word_index=9,
                    translation='银行', source_sentence='the bank approved the loan',
                )
                await db.commit()

            async with session_factory() as db:
                anns = await annotation_service.get_article_annotations(db, aid, uid)
            assert anns['0-3']['translation'] == '河岸'
            assert anns['1-9']['translation'] == '银行'
        finally:
            await _cleanup_anns(session_factory, uid)

    _run(scenario)


def test_get_annotations_skips_stale():
    uid = str(uuid4())
    aid = str(uuid4())

    async def scenario(session_factory):
        try:
            await _seed_article(session_factory, aid, uid)
            async with session_factory() as db:
                ann = await annotation_service.upsert_annotation(
                    db, aid, uid, 'bank', sentence_index=0, word_index=3, translation='河岸',
                )
                ann.is_stale = True
                await db.commit()

            async with session_factory() as db:
                anns = await annotation_service.get_article_annotations(db, aid, uid)
            assert '0-3' not in anns
        finally:
            await _cleanup_anns(session_factory, uid)

    _run(scenario)


def test_translate_endpoint_writes_position_annotation():
    """translate router upserts annotation keyed by the clicked position."""
    uid = str(uuid4())   # user_id is VARCHAR(36) — do NOT prefix (overflows)
    aid = str(uuid4())

    async def scenario(session_factory):
        try:
            # seed an article the user owns (article_id has an enforced FK to articles.id)
            await _seed_article(session_factory, aid, uid)
            async with session_factory() as db:
                await annotation_service.upsert_annotation(
                    db, aid, uid, "bank", sentence_index=0, word_index=1,
                    translation="银行", source_sentence="the bank",
                )
                await db.commit()
            async with session_factory() as db:
                anns = await annotation_service.get_article_annotations(db, aid, uid)
            assert anns["0-1"]["translation"] == "银行"
        finally:
            await _cleanup_anns(session_factory, uid)

    _run(scenario)
