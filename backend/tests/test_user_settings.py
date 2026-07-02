from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base
from app.main import app
from app.models.article import Article
from app.models.user import User
from app.routers import settings as settings_router
from app.routers import translate as translate_router
from app.schemas.translate import TranslateRequest
from app.services import paragraph_service
from app.services import settings_service
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


def test_settings_endpoint_requires_authentication():
    with TestClient(app) as client:
        response = client.get("/api/v1/settings")

    assert response.status_code == 401


def test_settings_are_stored_per_user(monkeypatch, tmp_path):
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({
        "ai_provider": "deepseek",
        "use_free_translation_fallback": False,
        "auto_open_sidebar_on_mark": False,
    }))
    monkeypatch.setattr(settings_service, "_PATH", settings_file)

    user_a = User(id=str(uuid4()), email=f"{uuid4()}@example.com", hashed_password="x")
    user_b = User(id=str(uuid4()), email=f"{uuid4()}@example.com", hashed_password="x")

    async def scenario(session_factory):
        try:
            async with session_factory() as db:
                db.add_all([user_a, user_b])
                await db.commit()

            async with session_factory() as db:
                updated = await settings_router.update_settings(
                    settings_router.SettingsIn(
                        use_free_translation_fallback=True,
                        auto_open_sidebar_on_mark=True,
                    ),
                    db=db,
                    current_user=user_a,
                )

            async with session_factory() as db:
                other_user_settings = await settings_router.get_settings(
                    db=db,
                    current_user=user_b,
                )

            assert updated.use_free_translation_fallback is True
            assert updated.auto_open_sidebar_on_mark is True
            assert other_user_settings.use_free_translation_fallback is False
            assert other_user_settings.auto_open_sidebar_on_mark is False
        finally:
            async with session_factory() as db:
                await db.execute(delete(User).where(User.id.in_([user_a.id, user_b.id])))
                await db.commit()

    _run(scenario)


def test_translate_word_uses_current_user_fallback_preference(monkeypatch, tmp_path):
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({
        "ai_provider": "deepseek",
        "use_free_translation_fallback": True,
        "auto_open_sidebar_on_mark": True,
    }))
    monkeypatch.setattr(settings_service, "_PATH", settings_file)

    user = User(id=str(uuid4()), email=f"{uuid4()}@example.com", hashed_password="x")
    article_id = str(uuid4())
    observed_fallback_values: list[bool | None] = []

    async def fake_translate(word: str, sentence: str, *, use_fallback: bool | None = None):
        observed_fallback_values.append(use_fallback)
        return SimpleNamespace(translation="银行", is_fallback=False)

    monkeypatch.setattr(
        translate_router,
        "translate_in_context_with_fallback",
        fake_translate,
    )

    async def scenario(session_factory):
        try:
            async with session_factory() as db:
                db.add(user)
                article = Article(
                    id=article_id,
                    user_id=user.id,
                    title="Fallback preference",
                    raw_text="The bank.",
                    tokens=[],
                    sentences=[],
                    word_count=0,
                )
                db.add(article)
                await db.flush()
                await paragraph_service.replace_article_paragraphs(db, article, article.raw_text)
                await settings_service.save_user_preferences(
                    db,
                    user.id,
                    {"use_free_translation_fallback": False},
                )
                link = (await paragraph_service.get_article_paragraphs(db, article.id))[0][0]

            async with session_factory() as db:
                await translate_router.translate_word(
                    TranslateRequest(
                        word="bank",
                        lemma="bank",
                        sentence="The bank.",
                        article_id=article_id,
                        article_paragraph_id=link.id,
                        sentence_index=0,
                        word_index=1,
                    ),
                    db=db,
                    current_user=user,
                )

            assert observed_fallback_values == [False]
        finally:
            async with session_factory() as db:
                await db.execute(delete(Article).where(Article.id == article_id))
                await db.execute(delete(User).where(User.id == user.id))
                await db.commit()

    _run(scenario)
