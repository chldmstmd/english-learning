from __future__ import annotations

"""
Regression tests for stuck-translation recovery.

A batch translation runs as a fire-and-forget asyncio task that flips an
article to `processing` before calling the AI. If the process is killed (or
the task is GC'd) mid-flight, the `except` branch that would set `failed`
never runs, so the article is stranded in `processing` forever — and the
trigger endpoints refuse to re-run a `processing` article, deadlocking it.

`recover_stuck_translations` is the startup sweep that breaks this deadlock:
any article left in `processing` when the process boots can only be a corpse
from a dead task, so it is reset to `failed` (which the UI offers a retry on).

These run against the real dockerized Postgres; each test seeds and cleans up
its own uniquely-id'd rows so it stays isolated.
"""
import asyncio
from uuid import uuid4

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.config import settings
from app.models.article import Article
from app.services.schema_service import ensure_runtime_schema
from app.models.user import User
from app.routers import articles as articles_router
from app.services import batch_translation_service


def _run(coro_fn):
    """Run an async scenario on a fresh engine bound to this call's event loop.

    The app's shared engine binds its pool to whatever loop imports it first;
    asyncio.run() makes a new loop each call, so we build a throwaway engine
    inside the loop and dispose it after.
    """
    async def wrapper():
        engine = create_async_engine(settings.database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with engine.begin() as conn:
                await ensure_runtime_schema(conn)
            await coro_fn(session_factory)
        finally:
            await engine.dispose()

    asyncio.run(wrapper())


def _make_article(status: str) -> Article:
    return Article(
        id=str(uuid4()),
        user_id="test-recovery-user",
        title="recovery-test",
        raw_text="hello world",
        tokens=[],
        sentences=[],
        word_count=2,
        translation_status=status,
    )


async def _seed(session_factory, *articles: Article) -> None:
    async with session_factory() as db:
        for a in articles:
            db.add(a)
        await db.commit()


async def _status_of(session_factory, article_id: str) -> str | None:
    async with session_factory() as db:
        return await db.scalar(
            select(Article.translation_status).where(Article.id == article_id)
        )


async def _cleanup(session_factory, *article_ids: str) -> None:
    async with session_factory() as db:
        await db.execute(delete(Article).where(Article.id.in_(article_ids)))
        await db.commit()


def test_recover_resets_processing_to_failed():
    stuck = _make_article("processing")

    async def scenario(session_factory):
        await _seed(session_factory, stuck)
        try:
            async with session_factory() as db:
                count = await batch_translation_service.recover_stuck_translations(db)
            assert count >= 1
            assert await _status_of(session_factory, stuck.id) == "failed"
        finally:
            await _cleanup(session_factory, stuck.id)

    _run(scenario)


def test_recover_leaves_other_statuses_untouched():
    done = _make_article("done")
    untranslated = _make_article("untranslated")
    failed = _make_article("failed")

    async def scenario(session_factory):
        await _seed(session_factory, done, untranslated, failed)
        try:
            async with session_factory() as db:
                await batch_translation_service.recover_stuck_translations(db)
            assert await _status_of(session_factory, done.id) == "done"
            assert await _status_of(session_factory, untranslated.id) == "untranslated"
            assert await _status_of(session_factory, failed.id) == "failed"
        finally:
            await _cleanup(session_factory, done.id, untranslated.id, failed.id)

    _run(scenario)


def test_translate_route_spawns_without_preemptive_processing(monkeypatch):
    user_id = str(uuid4())
    article = Article(
        id=str(uuid4()),
        user_id=user_id,
        title="route-spawn-test",
        raw_text="hello world",
        tokens=[],
        sentences=[],
        word_count=2,
        translation_status="untranslated",
    )
    spawned: list[str] = []

    monkeypatch.setattr(
        articles_router.batch_translation_service,
        "spawn_translation",
        lambda article_id: spawned.append(article_id),
    )

    async def scenario(session_factory):
        await _seed(session_factory, article)
        try:
            async with session_factory() as db:
                result = await articles_router.translate_article(
                    article.id,
                    db=db,
                    current_user=User(id=user_id, email="route@example.com", hashed_password="x"),
                )

            assert result["translation_status"] == "processing"
            assert result["translation_progress"]["total_words"] == 0
            assert spawned == [article.id]
            assert await _status_of(session_factory, article.id) == "untranslated"
        finally:
            await _cleanup(session_factory, article.id)

    _run(scenario)
