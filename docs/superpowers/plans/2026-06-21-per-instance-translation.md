# 按位置翻译 + 单词表重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 点击文中单词时，只翻译/标记被点击的那一处（按 token 位置），并按本句精准翻译；用户的生词在所有文章里按词（lemma）高亮提示；单词表展示词典义 + 点击位置链接。

**Architecture:** 双轨模型 —— 轨道 A（生词高亮）按 lemma 跨文章，纯前端用「文章 lemma ∩ 生词本 lemma」计算；轨道 B（点击处译文）按 token 位置 `(sentence_index, word_index)` 持久化在 `article_annotations` 表，自带译文文本（approach B）。删除原有跨文章预翻译机制（与省 token 目标冲突）。原文编辑后用「位置 → lemma 校验」标记失效标注，避免错位误导。

**Tech Stack:** FastAPI + SQLAlchemy(async) + PostgreSQL（后端，pytest 集成测试跑真实 Docker Postgres）；React + Zustand + TanStack Query + Tailwind（前端，无测试框架，用运行中的 app 人工验证）。

## Global Constraints

- 后端异步风格（async/await），与现有代码保持一致。
- 数据库无 Alembic 迁移；表通过 `create_all` 在 startup 自动建。**改 ORM 列/约束后，已存在的表不会被自动 ALTER —— 必须先 DROP 旧表再让 startup 重建。**
- `article_annotations` 旧数据可丢弃（标注可由用户重新点击再生）。
- 目标语言写死 `zh-CN`（本地化暂不做，不引入 `target_lang` 旋钮）。
- AI token 节流（mm4）：只翻用户点击的那一处；不预先翻译；单词表中文义用 `free_translation_service`（Google 翻译，非 AI token）。
- 后端测试沿用 `backend/tests/test_translation_recovery.py` 的 `_run/_seed/_cleanup` 模式（真实 Postgres，自清理唯一 id 行），用 `.venv/bin/python -m pytest` 运行。
- `token.index` 即 spaCy `token.i`，是**整篇文章内全局唯一**的索引；标注按位置存时用 `(sentence_index, word_index)` 复合键，前端字典键统一为字符串 `"{sentence_index}-{word_index}"`。
- 提交信息结尾加：`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

## File Structure

**后端**
- `backend/app/models/annotation.py` — 改：位置化 schema（新列 + 改唯一约束）
- `backend/app/services/annotation_service.py` — 重写：位置 upsert / 位置键查询 / 位置失效校验 / 按 lemma 反查位置；删除跨文章预翻译函数
- `backend/app/routers/translate.py` — 改：按位置 upsert，删 sync 调用，补 vocab 中文义
- `backend/app/routers/articles.py` — 改：`get_article` 位置键返回、`create_article` 去预埋、`edit_article` 加失效校验、删 pending 轮询触发
- `backend/app/routers/library.py` — 改：删懒同步，位置键返回
- `backend/app/routers/vocab.py` + `backend/app/schemas/vocab.py` — 改：`VocabDetailResponse` 增 `locations`
- `backend/tests/test_position_annotations.py` — 新建：位置标注测试
- `backend/tests/test_edit_fallback.py` — 新建：编辑失效测试
- `backend/tests/test_vocab_locations.py` — 新建：位置链接测试

**前端**
- `frontend/src/types/index.ts` — 改：`Annotation`/`VocabDetail` 类型
- `frontend/src/store/vocabStore.ts` — 改：标注按复合键
- `frontend/src/pages/ArticleReaderPage.tsx` + `frontend/src/pages/LibraryReaderPage.tsx` — 改：位置键初始化、删 pending 轮询、`?sentence=` 滚动
- `frontend/src/components/WordToken.tsx` — 改：按位置显示译文、按 lemma 高亮、点击两态
- `frontend/src/components/WordSidebar.tsx` — 改：常显中文义 + 位置链接
- `frontend/src/pages/VocabListPage.tsx` — 改：展示中文义（来自词典）+ 状态

---

## Task 1: 位置化 `ArticleAnnotation` 模型 + 重建表

**Files:**
- Modify: `backend/app/models/annotation.py`
- Test: `backend/tests/test_position_annotations.py`

**Interfaces:**
- Produces: `ArticleAnnotation` 列 `sentence_index:int`、`word_index:int`、`is_stale:bool`（默认 False）；唯一约束 `uq_annotation_position = (article_id, user_id, sentence_index, word_index)`；保留 `word`(lemma)、`translation`、`source_sentence`、`is_fallback`、`gen_status`、`created_at`。

- [ ] **Step 1: 写失败测试** — 断言新表结构

Create `backend/tests/test_position_annotations.py`:

```python
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
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_position_annotations.py::test_table_has_position_schema -v`
Expected: FAIL（旧表无 `sentence_index` 列，或唯一约束名不符）

- [ ] **Step 3: 改模型**

Replace `backend/app/models/annotation.py` entirely with:

```python
from datetime import datetime
from uuid import uuid4

from sqlalchemy import String, Text, Boolean, Integer, DateTime, UniqueConstraint, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ArticleAnnotation(Base):
    __tablename__ = "article_annotations"
    __table_args__ = (
        UniqueConstraint(
            "article_id", "user_id", "sentence_index", "word_index",
            name="uq_annotation_position",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    article_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    sentence_index: Mapped[int] = mapped_column(Integer, nullable=False)
    word_index: Mapped[int] = mapped_column(Integer, nullable=False)
    word: Mapped[str] = mapped_column(String(100), nullable=False)  # lemma, for vocab→locations lookup
    translation: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_sentence: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # always "done" under per-instance model (no more pending pre-seeding); kept for type compat
    gen_status: Mapped[str] = mapped_column(String(20), nullable=False, default="done")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 4: 删除旧表并按新 schema 重建**

旧表不会被 `create_all` 自动 ALTER，必须先 DROP 再重建。DB 已在 docker compose 运行中。执行（一步完成 drop + create，无需重启 uvicorn）：
```bash
cd backend && docker compose -f ../docker-compose.yml exec -T db psql -U postgres -d english_learning -c 'DROP TABLE IF EXISTS article_annotations CASCADE;' && .venv/bin/python -c "
import asyncio
from app.database import engine, Base
import app.models.annotation  # register the model on Base.metadata
async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
asyncio.run(main())
print('recreated')
"
```
Expected: prints `recreated`

- [ ] **Step 5: 运行测试，确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/test_position_annotations.py::test_table_has_position_schema -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/models/annotation.py backend/tests/test_position_annotations.py
git commit -m "$(printf 'feat: position-based article_annotations schema\n\nKey annotations by (article_id, user_id, sentence_index, word_index)\ninstead of by lemma, with is_stale flag for edit-invalidation.\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## Task 2: 重写 `annotation_service`（位置 upsert / 位置键查询 / 失效校验 / 位置反查）

**Files:**
- Modify: `backend/app/services/annotation_service.py`
- Test: `backend/tests/test_position_annotations.py` (append)

**Interfaces:**
- Consumes: `ArticleAnnotation`（Task 1）；`app.models.article.Article`。
- Produces:
  - `async upsert_annotation(db, article_id, user_id, word, sentence_index, word_index, translation=None, source_sentence=None, is_fallback=False, gen_status="done") -> ArticleAnnotation`
  - `async get_article_annotations(db, article_id, user_id) -> dict[str, dict]` 返回 `{ "{sidx}-{widx}": {translation, source_sentence, is_fallback, gen_status, is_stale} }`，跳过 `is_stale=True` 的项（正文不显示失效译文）。
  - `async get_word_click_locations(db, user_id, word, limit=3) -> list[dict]` 返回最近点击位置 `[{article_id, article_title, is_library, sentence_index, source_sentence, is_stale}]`（按 `created_at` 倒序）。
  - `async revalidate_article_annotations(db, article_id, tokens) -> None` 对该文章所有用户的标注：若新 `tokens` 中 `(sentence_index, word_index)` 处的 lemma 与 `word` 不一致或越界，则置 `is_stale=True`，否则置 `is_stale=False`。
  - 删除：`sync_word_to_user_articles_task`、`generate_pending_translations_task`、`get_pending_annotations`。

- [ ] **Step 1: 写失败测试** — 位置 upsert 与位置键查询

Append to `backend/tests/test_position_annotations.py`:

**Note:** `article_annotations.article_id` has an enforced FK to `articles.id`, and `user_id`/`article_id` are `String(36)` — so tests must seed an `articles` row first and use bare `str(uuid4())` (no prefix). This file's header (from Task 1) needs `from app.models.article import Article` added.

Append to `backend/tests/test_position_annotations.py` (and add the `Article` import at top):

```python
async def _seed_article(session_factory, article_id, user_id):
    async with session_factory() as db:
        db.add(Article(
            id=article_id, user_id=user_id, title="t", raw_text="x",
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
                    db, aid, uid, "bank", sentence_index=0, word_index=3,
                    translation="河岸", source_sentence="by the bank of the river",
                )
                await annotation_service.upsert_annotation(
                    db, aid, uid, "bank", sentence_index=1, word_index=9,
                    translation="银行", source_sentence="the bank approved the loan",
                )
                await db.commit()

            async with session_factory() as db:
                anns = await annotation_service.get_article_annotations(db, aid, uid)
            assert anns["0-3"]["translation"] == "河岸"
            assert anns["1-9"]["translation"] == "银行"
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
                    db, aid, uid, "bank", sentence_index=0, word_index=3, translation="河岸",
                )
                ann.is_stale = True
                await db.commit()

            async with session_factory() as db:
                anns = await annotation_service.get_article_annotations(db, aid, uid)
            assert "0-3" not in anns
        finally:
            await _cleanup_anns(session_factory, uid)

    _run(scenario)
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_position_annotations.py -v`
Expected: FAIL（`upsert_annotation` 旧签名无 `sentence_index` 关键字 → TypeError）

- [ ] **Step 3: 重写 service**

Replace `backend/app/services/annotation_service.py` entirely with:

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.annotation import ArticleAnnotation
from app.models.article import Article


def _key(sentence_index: int, word_index: int) -> str:
    return f"{sentence_index}-{word_index}"


async def get_article_annotations(
    db: AsyncSession, article_id: str, user_id: str
) -> dict[str, dict]:
    """Return {"{sidx}-{widx}": annotation_dict} for a given article, skipping stale ones."""
    rows = list(await db.scalars(
        select(ArticleAnnotation).where(
            ArticleAnnotation.article_id == article_id,
            ArticleAnnotation.user_id == user_id,
        )
    ))
    return {
        _key(ann.sentence_index, ann.word_index): {
            "translation": ann.translation,
            "source_sentence": ann.source_sentence,
            "is_fallback": ann.is_fallback,
            "gen_status": ann.gen_status,
            "is_stale": ann.is_stale,
        }
        for ann in rows
        if not ann.is_stale
    }


async def upsert_annotation(
    db: AsyncSession,
    article_id: str,
    user_id: str,
    word: str,
    sentence_index: int,
    word_index: int,
    translation: str | None = None,
    source_sentence: str | None = None,
    is_fallback: bool = False,
    gen_status: str = "done",
) -> ArticleAnnotation:
    existing = await db.scalar(
        select(ArticleAnnotation).where(
            ArticleAnnotation.article_id == article_id,
            ArticleAnnotation.user_id == user_id,
            ArticleAnnotation.sentence_index == sentence_index,
            ArticleAnnotation.word_index == word_index,
        )
    )
    if existing:
        existing.word = word
        existing.translation = translation
        existing.source_sentence = source_sentence
        existing.is_fallback = is_fallback
        existing.gen_status = gen_status
        existing.is_stale = False
        await db.flush()
        return existing

    ann = ArticleAnnotation(
        article_id=article_id,
        user_id=user_id,
        word=word,
        sentence_index=sentence_index,
        word_index=word_index,
        translation=translation,
        source_sentence=source_sentence,
        is_fallback=is_fallback,
        gen_status=gen_status,
        is_stale=False,
    )
    db.add(ann)
    await db.flush()
    return ann


async def get_word_click_locations(
    db: AsyncSession, user_id: str, word: str, limit: int = 3
) -> list[dict]:
    """Recent positions where the user clicked this lemma, newest first."""
    rows = list(await db.execute(
        select(ArticleAnnotation, Article.title, Article.is_library)
        .join(Article, Article.id == ArticleAnnotation.article_id)
        .where(
            ArticleAnnotation.user_id == user_id,
            ArticleAnnotation.word == word,
        )
        .order_by(ArticleAnnotation.created_at.desc())
        .limit(limit)
    ))
    return [
        {
            "article_id": ann.article_id,
            "article_title": title,
            "is_library": bool(is_library),
            "sentence_index": ann.sentence_index,
            "source_sentence": ann.source_sentence,
            "is_stale": ann.is_stale,
        }
        for ann, title, is_library in rows
    ]


async def revalidate_article_annotations(
    db: AsyncSession, article_id: str, tokens: list[dict]
) -> None:
    """
    After an article is re-tokenized, mark annotations stale when the token now
    sitting at (sentence_index, word_index) no longer has the same lemma.
    Sweeps ALL users' annotations for this article. Caller commits.
    """
    # Map (sentence_index, word_index) -> lemma from the new tokens.
    pos_lemma = {
        (t["sentence_index"], t["index"]): t.get("lemma")
        for t in tokens
        if t.get("is_alpha")
    }
    rows = list(await db.scalars(
        select(ArticleAnnotation).where(ArticleAnnotation.article_id == article_id)
    ))
    for ann in rows:
        current = pos_lemma.get((ann.sentence_index, ann.word_index))
        ann.is_stale = current != ann.word
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/test_position_annotations.py -v`
Expected: PASS（3 个测试全过）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/annotation_service.py backend/tests/test_position_annotations.py
git commit -m "$(printf 'feat: position-based annotation service + location lookup\n\nupsert/get by (sentence_index, word_index); get_word_click_locations\nfor vocab links; revalidate_article_annotations for edit fallback.\nRemove cross-article pre-translation tasks.\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## Task 3: `/translate-word` 按位置 upsert + 删 sync + 补 vocab 中文义

**Files:**
- Modify: `backend/app/routers/translate.py`
- Test: `backend/tests/test_position_annotations.py` (append)

**Interfaces:**
- Consumes: `annotation_service.upsert_annotation`（Task 2，位置签名）；`free_translation_service.translate(word) -> str`；`vocab_service.upsert_word`。
- Produces: `POST /translate-word` 行为：按位置写标注；不再调用任何跨文章 sync；首次入库的生词补一个词典级中文义到 `vocab.context_translation`（best-effort，非 AI token）。

- [ ] **Step 1: 写失败测试** — 翻译后产生位置键标注

Append to `backend/tests/test_position_annotations.py`:

```python
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
```

(`_seed_article` and `_cleanup_anns` helpers already exist in this file from Task 2; `delete`/`Article` already imported at top.)

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_position_annotations.py::test_translate_endpoint_writes_position_annotation -v`
Expected: 在 Task 2 已重写 service 的前提下此测试应已 PASS（它验证 service 契约）。若 FAIL，先修 Task 2。本任务真正改动在 router；该测试锁定契约。

- [ ] **Step 3: 改 translate 路由**

In `backend/app/routers/translate.py`, replace the body of `translate_word` from the `await annotation_service.upsert_annotation(...)` block onward, and the import line. Final file:

```python
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.article import Article
from app.models.article_translation import ArticleTranslation
from app.models.user import User
from app.schemas.translate import TranslateRequest, TranslateResponse
from app.services import ai_service, free_translation_service, settings_service, vocab_service, annotation_service

router = APIRouter(tags=["translate"])


async def _get_translation_with_fallback(word: str, sentence: str) -> tuple[str, bool]:
    try:
        translation = await ai_service.translate_in_context(word, sentence)
        return translation, False
    except Exception:
        if not settings_service.load().get("use_free_translation_fallback", True):
            raise HTTPException(status_code=503, detail="AI translation unavailable")
        try:
            translation = await free_translation_service.translate(word)
            return translation, True
        except Exception:
            raise HTTPException(status_code=503, detail="All translation services unavailable")


@router.post("/translate-word", response_model=TranslateResponse)
async def translate_word(
    body: TranslateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    article = await db.scalar(
        select(Article).where(
            Article.id == body.article_id,
            or_(Article.user_id == current_user.id, Article.is_library == True),  # noqa: E712
        )
    )
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    if body.sentence_index is None or body.word_index is None:
        raise HTTPException(status_code=422, detail="sentence_index and word_index are required")

    vocab = await vocab_service.upsert_word(
        db, current_user.id, body.lemma, source_sentence=body.sentence
    )

    # Dictionary-level Chinese meaning for the vocab list (word-level, context-free,
    # via free translation — not AI tokens). Best-effort, only when missing.
    if not vocab.context_translation:
        try:
            vocab.context_translation = await free_translation_service.translate(body.lemma)
        except Exception:
            pass  # leave null; vocab detail can fill it later

    # Check batch translation cache (per position)
    cached = await db.scalar(
        select(ArticleTranslation).where(
            ArticleTranslation.article_id == body.article_id,
            ArticleTranslation.sentence_index == body.sentence_index,
            ArticleTranslation.word_index == body.word_index,
        )
    )
    if cached and cached.translation:
        translation, is_fallback = cached.translation, False
    else:
        translation, is_fallback = await _get_translation_with_fallback(body.lemma, body.sentence)

    await annotation_service.upsert_annotation(
        db,
        body.article_id,
        current_user.id,
        body.lemma,
        sentence_index=body.sentence_index,
        word_index=body.word_index,
        translation=translation,
        source_sentence=body.sentence,
        is_fallback=is_fallback,
        gen_status="done",
    )

    await db.commit()

    return TranslateResponse(
        word=body.word,
        lemma=body.lemma,
        translation=translation,
        is_fallback=is_fallback,
        status=vocab.status,
    )
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/test_position_annotations.py -v`
Expected: PASS

- [ ] **Step 5: 确认无残留 sync 引用 + 后端可导入**

Run:
```bash
cd backend && grep -rn "sync_word_to_user_articles_task" app/ | grep -v __pycache__ ; .venv/bin/python -c "import app.routers.translate; print('import ok')"
```
Expected: grep 在 `translate.py` 中无结果（其它文件将在 Task 4/5 清理）；打印 `import ok`

- [ ] **Step 6: 提交**

```bash
git add backend/app/routers/translate.py backend/tests/test_position_annotations.py
git commit -m "$(printf 'feat: translate-word upserts by position, drops cross-article sync\n\nWrite annotation keyed by clicked (sentence_index, word_index); seed\nvocab Chinese meaning via free translation; no more background sync.\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## Task 4: `articles.py` —— 位置键返回、去预埋、编辑失效校验

**Files:**
- Modify: `backend/app/routers/articles.py`
- Test: `backend/tests/test_edit_fallback.py`

**Interfaces:**
- Consumes: `annotation_service.revalidate_article_annotations(db, article_id, tokens)`、`get_article_annotations`（Task 2）；`nlp_service.tokenize`。
- Produces: `get_article` 返回的 `annotations` 为位置键 dict、不再触发 pending 任务；`create_article` 不再为已知生词预埋 pending 标注；`edit_article` 重新 tokenize 后调用 `revalidate_article_annotations`。

- [ ] **Step 1: 写失败测试** — 编辑后位置错位的标注被标 stale

Create `backend/tests/test_edit_fallback.py`:

```python
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
```

> 注：此文件 (`test_edit_fallback.py`) 顶部 import 需包含 `from app.models.article import Article`（已在 Step 1 文件头），且 `from sqlalchemy import select, delete`。

- [ ] **Step 2: 运行测试，确认失败/通过**

Run: `cd backend && .venv/bin/python -m pytest tests/test_edit_fallback.py -v`
Expected: 验证 `revalidate_article_annotations`（Task 2 已实现）→ 应 PASS。若 FAIL 回查 Task 2。

- [ ] **Step 3: 改 `create_article`** — 删掉为已知生词预埋 pending 的循环

In `backend/app/routers/articles.py`, in `create_article`, delete these lines (currently ~46-53):

```python
    word_statuses = await vocab_service.get_all_word_statuses(db, current_user.id)
    article_lemmas = {t["lemma"] for t in tokens if t["is_alpha"]}
    for word in word_statuses:
        if word in article_lemmas:
            await annotation_service.upsert_annotation(
                db, article.id, current_user.id, word, gen_status="pending"
            )
```

So the function ends:
```python
    db.add(article)
    await db.flush()

    await db.commit()
    return ArticleListItem.model_validate(article)
```

- [ ] **Step 4: 改 `edit_article`** — 重新 tokenize 后校验标注失效

In `edit_article`, after `article.translation_status = "stale"` and before the sentence-count reset block, add:

```python
    # Position annotations may now point at different words -> mark mismatches stale.
    await annotation_service.revalidate_article_annotations(db, article_id, tokens)
```

- [ ] **Step 5: 改 `get_article`** — 去掉 pending 后台触发（标注已无 pending）

In `get_article`, delete the block (currently ~215-219):
```python
    has_pending = any(a["gen_status"] == "pending" for a in annotations.values())
    if has_pending:
        background_tasks.add_task(
            annotation_service.generate_pending_translations_task, article_id, current_user.id
        )
```
`annotations = await annotation_service.get_article_annotations(...)` already returns the position-keyed dict, so the `ArticleDetailResponse(..., annotations=annotations, ...)` line is unchanged. `BackgroundTasks` param can stay (still used? check) — if now unused, leave the import/param to avoid churn; it is harmless.

- [ ] **Step 6: 运行测试 + 导入检查**

Run:
```bash
cd backend && .venv/bin/python -m pytest tests/test_edit_fallback.py -v && .venv/bin/python -c "import app.routers.articles; print('import ok')"
```
Expected: PASS + `import ok`

- [ ] **Step 7: 提交**

```bash
git add backend/app/routers/articles.py backend/tests/test_edit_fallback.py
git commit -m "$(printf 'feat: articles router position annotations + edit fallback\n\nget_article returns position-keyed annotations; drop pending pre-seed\nin create_article; revalidate (stale) annotations on edit_article.\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## Task 5: `library.py` + `books.py` —— 删除跨文章/章节预埋同步、位置键返回

**Files:**
- Modify: `backend/app/routers/library.py`
- Modify: `backend/app/routers/books.py`

**Interfaces:**
- Consumes: `annotation_service.get_article_annotations`（Task 2，位置键）。
- Produces: `GET /library/{article_id}` 不再为生词懒创建 pending 标注、不再触发 `generate_pending_translations_task`；`annotations` 为位置键 dict。`POST /books/{book_id}/chapters` 创建章节时不再为已知生词预埋 pending 标注（与 `create_article` 一致；旧调用用的是已删除的 lemma 签名，会 TypeError）。

- [ ] **Step 1: 删除 library 懒同步块**

In `backend/app/routers/library.py` `get_library_article`, replace the block currently at lines ~209-233 (from the `# Lazy annotation sync:` comment through the `has_pending`/background_tasks `if`) with:

```python
    await db.commit()

    annotations = await annotation_service.get_article_annotations(db, article_id, current_user.id)
    word_statuses = await vocab_service.get_all_word_statuses(db, current_user.id)
    article_lemmas = {t["lemma"] for t in article.tokens if t["is_alpha"]}
    article_word_statuses = {w: s for w, s in word_statuses.items() if w in article_lemmas}
```

- [ ] **Step 2: 删除 books 章节创建里的预埋块**

In `backend/app/routers/books.py` `create_chapter` (或相应的章节创建函数)，删除以下预埋循环（当前 ~142-148）：

```python
    word_statuses = await vocab_service.get_all_word_statuses(db, current_user.id)
    article_lemmas = {t["lemma"] for t in tokens if t["is_alpha"]}
    for word in word_statuses:
        if word in article_lemmas:
            await annotation_service.upsert_annotation(
                db, article.id, current_user.id, word, gen_status="pending"
            )
```

使该函数从 `db.add(article)` / `await db.flush()` 直接进入：
```python
    db.add(article)
    await db.flush()

    await db.commit()
    asyncio.create_task(batch_translation_service.translate_article(article.id))
    return ArticleListItem.model_validate(article)
```

> 注：若 `vocab_service` / `annotation_service` 的 import 在删除后于 `books.py` 内不再被任何其它代码使用，移除对应 import 以免 lint 噪音；若仍被使用则保留。删除前用 `grep -n "vocab_service\|annotation_service" app/routers/books.py` 确认。

- [ ] **Step 3: 确认无残留 pending/sync 引用 + 无旧签名 upsert 调用**

Run:
```bash
cd backend && grep -rn "generate_pending_translations_task\|sync_word_to_user_articles_task\|gen_status=\"pending\"" app/ | grep -v __pycache__
```
Expected: 无结果（全部已清除；注意此前 articles.py/translate.py 已在 Task 3/4 清理）

- [ ] **Step 4: 导入检查 + 全后端测试**

Run:
```bash
cd backend && .venv/bin/python -c "import app.routers.library, app.routers.books; print('import ok')" && .venv/bin/python -m pytest tests/ -v
```
Expected: `import ok` + 全部测试 PASS（包括既有的 test_translation_recovery / test_library_books 等未受影响）

- [ ] **Step 5: 提交**

```bash
git add backend/app/routers/library.py backend/app/routers/books.py
git commit -m "$(printf 'feat: drop cross-article/chapter pre-seed sync in library + books\n\nlibrary reader returns position-keyed annotations and stops lazy\npending sync; book chapter creation stops pre-seeding pending\nannotations for vocab words (old lemma signature is gone).\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## Task 6: 单词表详情加「点击位置链接」

**Files:**
- Modify: `backend/app/schemas/vocab.py`, `backend/app/routers/vocab.py`
- Test: `backend/tests/test_vocab_locations.py`

**Interfaces:**
- Consumes: `annotation_service.get_word_click_locations(db, user_id, word, limit=3)`（Task 2）。
- Produces: `VocabDetailResponse` 增加字段 `locations: list[dict]`（每项 `{article_id, article_title, is_library, sentence_index, source_sentence, is_stale}`）。

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_vocab_locations.py`:

```python
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
```

- [ ] **Step 2: 运行测试，确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/test_vocab_locations.py -v`
Expected: PASS（`get_word_click_locations` 已在 Task 2 实现）

- [ ] **Step 3: 扩展 schema**

In `backend/app/schemas/vocab.py`, change `VocabDetailResponse`:

```python
class VocabDetailResponse(BaseModel):
    word: str
    phonetic: str | None
    status: str
    context_translation: str | None
    source_sentence: str | None
    definitions: list[dict]
    locations: list[dict] = []
```

- [ ] **Step 4: 在路由里填充 locations + 懒补中文义**

In `backend/app/routers/vocab.py` `get_vocab_detail`, after fetching `dict_data` and before the `return`, add the locations fetch and a lazy Chinese-meaning fill, then include in the response:

```python
    locations = await annotation_service.get_word_click_locations(
        db, current_user.id, word, limit=3
    )

    # Lazily backfill the dictionary Chinese meaning if missing (free translation, not AI).
    if not vocab.context_translation:
        from app.services import free_translation_service
        try:
            vocab.context_translation = await free_translation_service.translate(word)
            await db.commit()
        except Exception:
            pass

    return VocabDetailResponse(
        word=vocab.word,
        phonetic=dict_data["phonetic"],
        status=vocab.status,
        context_translation=vocab.context_translation,
        source_sentence=vocab.source_sentence,
        definitions=dict_data["definitions"],
        locations=locations,
    )
```

And add `annotation_service` to the import line:
```python
from app.services import dict_service, vocab_service, annotation_service
```

- [ ] **Step 5: 运行测试 + 导入检查**

Run:
```bash
cd backend && .venv/bin/python -m pytest tests/test_vocab_locations.py -v && .venv/bin/python -c "import app.routers.vocab; print('import ok')"
```
Expected: PASS + `import ok`

- [ ] **Step 6: 提交**

```bash
git add backend/app/schemas/vocab.py backend/app/routers/vocab.py backend/tests/test_vocab_locations.py
git commit -m "$(printf 'feat: vocab detail exposes recent click locations\n\nReturn up to 3 most-recent positions where the user clicked the lemma,\nwith article title and staleness; lazily backfill Chinese meaning.\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## Task 7: 前端类型 + store 位置化 + 阅读页接线

**Files:**
- Modify: `frontend/src/types/index.ts`, `frontend/src/store/vocabStore.ts`, `frontend/src/pages/ArticleReaderPage.tsx`, `frontend/src/pages/LibraryReaderPage.tsx`

**Interfaces:**
- Consumes: 后端 `annotations` 现为 `Record<"{sidx}-{widx}", Annotation>`；`VocabDetail` 现含 `locations`。
- Produces:
  - `vocabStore`: `articleAnnotations: Record<string, Record<string, Annotation>>`（内层键为 `"{sidx}-{widx}"`）；`annotationKey(sentenceIndex, wordIndex): string`；`getAnnotation(articleId, sentenceIndex, wordIndex): Annotation | undefined`；`setAnnotation(articleId, sentenceIndex, wordIndex, annotation)`；保留 `wordStatuses` 按 lemma 的 `getStatus/setWordStatus`；`initFromArticle(articleId, wordStatuses, annotations)` 直接存后端返回的位置键 dict；移除 `mergeAnnotations`。
  - 阅读页：用位置键初始化、删除 pending 轮询、支持 `?sentence=N` 滚动定位。

- [ ] **Step 1: 改类型**

In `frontend/src/types/index.ts`, extend `Annotation` and `VocabDetail`:

```typescript
export interface Annotation {
  translation: string | null;
  source_sentence: string | null;
  is_fallback: boolean;
  gen_status: "pending" | "done" | "failed";
  is_stale?: boolean;
}

export interface VocabLocation {
  article_id: string;
  article_title: string;
  is_library: boolean;
  sentence_index: number;
  source_sentence: string | null;
  is_stale: boolean;
}
```

And add `locations` to `VocabDetail`:
```typescript
export interface VocabDetail {
  word: string;
  phonetic: string | null;
  status: WordStatus;
  context_translation: string | null;
  source_sentence: string | null;
  definitions: Array<{
    pos: string;
    definition: string;
    example: string;
  }>;
  locations: VocabLocation[];
}
```

- [ ] **Step 2: 重写 store**

Replace `frontend/src/store/vocabStore.ts` entirely with:

```typescript
import { create } from "zustand";
import type { Annotation, WordStatus } from "../types";

export const annotationKey = (sentenceIndex: number, wordIndex: number) =>
  `${sentenceIndex}-${wordIndex}`;

interface VocabStore {
  wordStatuses: Record<string, WordStatus>;
  articleAnnotations: Record<string, Record<string, Annotation>>;

  getStatus: (lemma: string) => WordStatus;
  getAnnotation: (articleId: string, sentenceIndex: number, wordIndex: number) => Annotation | undefined;
  setWordStatus: (lemma: string, status: WordStatus) => void;
  setAnnotation: (articleId: string, sentenceIndex: number, wordIndex: number, annotation: Annotation) => void;
  initFromArticle: (
    articleId: string,
    wordStatuses: Record<string, WordStatus>,
    annotations: Record<string, Annotation>
  ) => void;
}

export const useVocabStore = create<VocabStore>((set, get) => ({
  wordStatuses: {},
  articleAnnotations: {},

  getStatus: (lemma) => get().wordStatuses[lemma] ?? "unseen",

  getAnnotation: (articleId, sentenceIndex, wordIndex) =>
    get().articleAnnotations[articleId]?.[annotationKey(sentenceIndex, wordIndex)],

  setWordStatus: (lemma, status) =>
    set((s) => ({ wordStatuses: { ...s.wordStatuses, [lemma]: status } })),

  setAnnotation: (articleId, sentenceIndex, wordIndex, annotation) =>
    set((s) => ({
      articleAnnotations: {
        ...s.articleAnnotations,
        [articleId]: {
          ...(s.articleAnnotations[articleId] ?? {}),
          [annotationKey(sentenceIndex, wordIndex)]: annotation,
        },
      },
    })),

  initFromArticle: (articleId, wordStatuses, annotations) =>
    set((s) => ({
      wordStatuses: { ...s.wordStatuses, ...wordStatuses },
      articleAnnotations: { ...s.articleAnnotations, [articleId]: annotations },
    })),
}));
```

- [ ] **Step 3: 改 `ArticleReaderPage`** — 删轮询、加 `?sentence=` 滚动

In `frontend/src/pages/ArticleReaderPage.tsx`:

(a) Replace the store destructure (line 14):
```typescript
  const { initFromArticle } = useVocabStore();
```

(b) Add `useSearchParams` import and read the param. Change line 2 import:
```typescript
import { useParams, useSearchParams, Link } from "react-router-dom";
```
After `const { id } = useParams...`:
```typescript
  const [searchParams] = useSearchParams();
  const targetSentence = searchParams.get("sentence");
```

(c) Replace the scroll-restore effect (lines 40-48) so a `?sentence=` param wins over last-read:
```typescript
  // Scroll to ?sentence= target (from vocab location link) or last-read sentence
  useEffect(() => {
    if (!article) return;
    const idx = targetSentence != null ? Number(targetSentence) : article.last_sentence_index;
    if (idx && idx > 0) {
      const t = setTimeout(() => {
        document.querySelector(`[data-sentence-index="${idx}"]`)
          ?.scrollIntoView({ behavior: "auto", block: "center" });
      }, 100);
      return () => clearTimeout(t);
    }
  }, [article, targetSentence]);
```

(d) Delete the pending-poll machinery: remove `mergeAnnotations, articleAnnotations` from the destructure (done in (a)), delete the `hasPending` `useMemo` (lines ~72-76) and the `useQuery({ queryKey: ["annotations-poll", ...] })` block (lines ~78-90). Remove now-unused `useMemo` from the React import if nothing else uses it (check: `saveTimer`/`useRef` stay). Change line 1 to:
```typescript
import { useEffect, useRef } from "react";
```

- [ ] **Step 4: 改 `LibraryReaderPage`** — 删轮询、位置键初始化

In `frontend/src/pages/LibraryReaderPage.tsx`:

(a) Replace store destructure (line 20):
```typescript
  const { initFromArticle, articleAnnotations } = useVocabStore();
```
(`articleAnnotations` is still used by the bookmark-prompt effect at lines 57-72, which only checks `Object.keys(...).length` — that still works with position keys.)

(b) Delete the `hasPending` `useMemo` (lines ~74-77) and the `useQuery({ queryKey: ["library-annotations-poll", ...] })` block (lines ~79-92). Remove `useMemo` from React import (line 1) if unused elsewhere — `useState` stays:
```typescript
import { useEffect, useState } from "react";
```

- [ ] **Step 5: 验证 —— 前端构建通过**

Run: `cd frontend && npm run build`
Expected: TypeScript 编译通过，无类型错误（`mergeAnnotations`/旧 `getAnnotation(articleId, lemma)` 的残留会在 Task 8 修复；若此处因 WordToken 仍用旧签名而报错，**先做 Task 8 再回此步**，或临时确认报错仅来自 `WordToken.tsx`）。

> 注：Task 7 与 Task 8 共同构成一次可编译的前端状态。若分步构建报错仅指向 `WordToken.tsx`，属预期，Task 8 修复后整体应通过。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/types/index.ts frontend/src/store/vocabStore.ts frontend/src/pages/ArticleReaderPage.tsx frontend/src/pages/LibraryReaderPage.tsx
git commit -m "$(printf 'feat: position-keyed vocab store + reader wiring\n\nStore annotations by sentence-word key; drop pending polling (no more\npre-seeded annotations); support ?sentence= scroll from vocab links.\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## Task 8: `WordToken` —— 按位置显示译文、按 lemma 高亮、点击两态

**Files:**
- Modify: `frontend/src/components/WordToken.tsx`

**Interfaces:**
- Consumes: `useVocabStore` 的 `getStatus(lemma)`、`getAnnotation(articleId, sentenceIndex, wordIndex)`、`setWordStatus(lemma, status)`、`setAnnotation(articleId, sentenceIndex, wordIndex, annotation)`（Task 7）；`POST /translate-word`（Task 3，需 `sentence_index`/`word_index`）。
- Produces: 单词渲染规则 —— 高亮 = `lemma ∈ 生词本 且 status ∈ {new, reviewing}`（mastered/unseen 不高亮）；译文显示 = 该位置有非空 `annotation.translation`；点击两态（无译文→翻译并显示本处；有译文→开侧栏）。

- [ ] **Step 1: 重写组件**

Replace `frontend/src/components/WordToken.tsx` entirely with:

```typescript
import React from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../api/client";
import { useVocabStore } from "../store/vocabStore";
import { useSidebarStore } from "../store/sidebarStore";
import { cn } from "../utils/cn";
import type { Token, Sentence, TranslateResponse } from "../types";

// Single highlight for an in-progress vocab word (new/reviewing); mastered & unseen are unstyled.
const VOCAB_HIGHLIGHT =
  "underline decoration-amber-400 decoration-dashed underline-offset-4 cursor-pointer";

interface Props {
  token: Token;
  articleId: string;
  sentences: Sentence[];
  autoOpenSidebar: boolean;
}

export const WordToken: React.FC<Props> = ({ token, articleId, sentences, autoOpenSidebar }) => {
  const { getStatus, getAnnotation, setWordStatus, setAnnotation } = useVocabStore();
  const { open: openSidebar } = useSidebarStore();

  const status = getStatus(token.lemma);
  const annotation = getAnnotation(articleId, token.sentence_index, token.index);

  const getSentenceText = () =>
    sentences.find((s) => s.index === token.sentence_index)?.text ?? "";

  const translateMutation = useMutation({
    mutationFn: () =>
      api
        .post("translate-word", {
          json: {
            word: token.text,
            lemma: token.lemma,
            sentence: getSentenceText(),
            article_id: articleId,
            sentence_index: token.sentence_index,
            word_index: token.index,
          },
        })
        .json<TranslateResponse>(),
    onMutate: () => {
      // optimistic highlight only for brand-new words; never downgrade an
      // already-tracked word (reviewing/mastered) to "new" on click.
      if (getStatus(token.lemma) === "unseen") {
        setWordStatus(token.lemma, "new");
      }
    },
    onSuccess: (data) => {
      setWordStatus(token.lemma, data.status);
      setAnnotation(articleId, token.sentence_index, token.index, {
        translation: data.translation,
        source_sentence: getSentenceText(),
        is_fallback: data.is_fallback,
        gen_status: "done",
      });
    },
    onError: () => {
      // roll back optimistic highlight only if nothing else marked it
      if (getStatus(token.lemma) === "new" && !getAnnotation(articleId, token.sentence_index, token.index)) {
        setWordStatus(token.lemma, "unseen");
      }
    },
  });

  const showTranslation = !!annotation?.translation;
  // highlight = word is in vocab and not yet mastered
  const highlighted = status === "new" || status === "reviewing";

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (showTranslation) {
      // already translated here -> manage the word
      openSidebar(token.text, token.lemma, articleId, getSentenceText());
    } else {
      translateMutation.mutate();
      if (autoOpenSidebar) {
        openSidebar(token.text, token.lemma, articleId, getSentenceText());
      }
    }
  };

  // Non-clickable tokens (punctuation, numbers, etc.)
  if (token.is_punct || !token.is_alpha) {
    return (
      <>
        <span>{token.text}</span>
        {token.ws && <span>{token.ws}</span>}
      </>
    );
  }

  return (
    <>
      <ruby
        className={cn(
          "cursor-pointer rounded hover:bg-gray-100 transition-colors",
          highlighted && VOCAB_HIGHLIGHT
        )}
        onClick={handleClick}
        data-word={token.lemma}
        data-status={status}
        aria-label={
          showTranslation ? `${token.text}, 翻译: ${annotation!.translation}` : token.text
        }
      >
        {token.text}
        {showTranslation ? (
          <rt className="text-red-500 not-italic text-[11px]">
            {annotation!.translation}
            {annotation!.is_fallback && (
              <span className="text-gray-400 text-[9px] ml-0.5">*</span>
            )}
          </rt>
        ) : (
          <rt />
        )}
      </ruby>
      {token.ws && <span>{token.ws}</span>}
    </>
  );
};
```

- [ ] **Step 2: 验证 —— 前端构建通过**

Run: `cd frontend && npm run build`
Expected: 编译通过，无类型错误

- [ ] **Step 3: 验证 —— 真实点击行为（运行 app）**

确保后端已重启加载新代码、前端 `npm run dev` 运行中。在浏览器打开一篇含重复词的文章（或用一篇英文文章），人工核对：
1. 点击某个词的某一处 → **只有这一处**上方出现红字译文；同词其它位置不出现译文。
2. 该词全文所有位置（未掌握时）出现琥珀虚线高亮。
3. 再次点击**已显示译文**的那一处 → 打开侧栏（不重复翻译）。
4. 点击同一个词的**另一处** → 该处按它自己的句子翻译并显示（可与第一处不同）。
5. 刷新页面 → 已点击处的译文仍在（持久化）。

用 curl 验证后端契约（替换真实 token 与 article_id）：
```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/translate-word \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"word":"bank","lemma":"bank","sentence":"the bank approved the loan","article_id":"'"$AID"'","sentence_index":0,"word_index":1}' | python3 -m json.tool
```
Expected: 返回含 `translation` 的 JSON；再次 `GET /api/v1/articles/$AID` 的 `annotations` 含键 `"0-1"`。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/components/WordToken.tsx
git commit -m "$(printf 'feat: per-position translation display in WordToken\n\nTranslation shown only at the clicked position; single amber highlight\nfor in-progress vocab words; click toggles translate vs open sidebar.\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## Task 9: `WordSidebar` —— 常显中文义 + 词典释义 + 位置链接

**Files:**
- Modify: `frontend/src/components/WordSidebar.tsx`

**Interfaces:**
- Consumes: `GET /vocab/{lemma}/detail` 现含 `locations`（Task 6）+ `context_translation`（中文义）；`useNavigate`（react-router）。
- Produces: 侧栏始终展示中文义 + 词典释义 + 最近 3 处位置链接（点击跳转 `/articles/{id}?sentence=N` 或 `/library/{id}?sentence=N`）；保留「已掌握 / 再复习」状态操作。

- [ ] **Step 1: 重写组件主体**

Replace `frontend/src/components/WordSidebar.tsx` entirely with:

```typescript
import React, { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { X, Volume2, ArrowRight } from "lucide-react";
import { api } from "../api/client";
import { useSidebarStore } from "../store/sidebarStore";
import { useVocabStore } from "../store/vocabStore";
import type { VocabDetail } from "../types";

function speak(text: string) {
  if ("speechSynthesis" in window) {
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "en-US";
    window.speechSynthesis.speak(utterance);
  }
}

export const WordSidebar: React.FC = () => {
  const { isOpen, word, lemma, sourceSentence, close } = useSidebarStore();
  const { setWordStatus } = useVocabStore();
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [close]);

  const { data: detail, isLoading } = useQuery({
    queryKey: ["vocab-detail", lemma, sourceSentence],
    queryFn: () =>
      api
        .get(`vocab/${lemma}/detail`, {
          searchParams: sourceSentence ? { sentence: sourceSentence } : {},
        })
        .json<VocabDetail>(),
    enabled: isOpen && !!lemma,
    staleTime: 60_000,
  });

  const statusMutation = useMutation({
    mutationFn: ({ word, status }: { word: string; status: string }) =>
      api.patch(`vocab/${word}/status`, { json: { status } }),
    onSuccess: (_, { word: w, status }) => {
      setWordStatus(w, status as never);
      queryClient.invalidateQueries({ queryKey: ["vocab-detail", w] });
      queryClient.invalidateQueries({ queryKey: ["vocab"] });
    },
  });

  const goToLocation = (loc: VocabDetail["locations"][number]) => {
    const base = loc.is_library ? "/library" : "/articles";
    close();
    navigate(`${base}/${loc.article_id}?sentence=${loc.sentence_index}`);
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.aside
          key="sidebar"
          initial={{ x: "100%" }}
          animate={{ x: 0 }}
          exit={{ x: "100%" }}
          transition={{ type: "tween", duration: 0.2 }}
          className="fixed right-0 top-0 h-full w-80 bg-white border-l border-gray-200 shadow-xl flex flex-col z-50 overflow-y-auto"
        >
          {/* Header */}
          <div className="flex items-center justify-between p-5 border-b border-gray-100">
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-bold text-gray-900">{word}</h2>
              {detail?.phonetic && (
                <span className="text-sm text-gray-400">{detail.phonetic}</span>
              )}
              <button
                onClick={() => word && speak(word)}
                className="text-blue-400 hover:text-blue-600"
                aria-label="朗读"
              >
                <Volume2 size={16} />
              </button>
            </div>
            <button
              onClick={close}
              className="text-gray-400 hover:text-gray-600"
              aria-label="关闭"
            >
              <X size={20} />
            </button>
          </div>

          <div className="flex-1 p-5 flex flex-col gap-5">
            {/* Chinese meaning (dictionary, word-level) */}
            {detail?.context_translation && (
              <div className="bg-gray-50 border border-gray-100 rounded-lg p-4">
                <p className="text-xs text-gray-500 mb-1 uppercase tracking-wide">中文词义</p>
                <p className="text-lg font-semibold text-gray-900">{detail.context_translation}</p>
              </div>
            )}

            {isLoading && (
              <p className="text-sm text-gray-400 animate-pulse">加载中...</p>
            )}

            {/* English dictionary definitions */}
            {detail?.definitions && detail.definitions.length > 0 && (
              <section>
                <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
                  词典释义
                </h3>
                <div className="space-y-2">
                  {detail.definitions.map((def, i) => (
                    <div key={i}>
                      <span className="text-xs bg-gray-100 text-gray-500 rounded px-1.5 py-0.5 mr-1.5">
                        {def.pos}
                      </span>
                      <span className="text-sm text-gray-700">{def.definition}</span>
                      {def.example && (
                        <p className="text-xs text-gray-400 mt-0.5 italic pl-1">
                          {def.example}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* Click locations */}
            {detail?.locations && detail.locations.length > 0 && (
              <section>
                <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
                  你点过的位置
                </h3>
                <div className="space-y-2">
                  {detail.locations.map((loc, i) => (
                    <button
                      key={i}
                      onClick={() => goToLocation(loc)}
                      className="w-full text-left border border-gray-200 rounded-lg p-2.5 hover:border-amber-400 transition-colors group"
                    >
                      <div className="flex items-center gap-1.5 text-xs font-medium text-gray-700">
                        <span className="truncate">{loc.article_title}</span>
                        {loc.is_stale && (
                          <span className="text-amber-600 shrink-0">(原文已修改)</span>
                        )}
                        <ArrowRight size={11} className="ml-auto shrink-0 text-gray-300 group-hover:text-amber-500" />
                      </div>
                      {loc.source_sentence && (
                        <p className="text-xs text-gray-400 mt-0.5 line-clamp-2">{loc.source_sentence}</p>
                      )}
                    </button>
                  ))}
                </div>
              </section>
            )}
          </div>

          {/* Status actions — pinned to bottom */}
          {detail && detail.status !== "unseen" && (
            <div className="p-5 border-t border-gray-100 flex gap-2">
              {detail.status !== "mastered" ? (
                <button
                  onClick={() => {
                    if (lemma) statusMutation.mutate({ word: lemma, status: "mastered" });
                    close();
                  }}
                  className="flex-1 bg-green-500 text-white rounded-lg py-2.5 text-sm font-medium hover:bg-green-600 transition-colors"
                >
                  标记已掌握
                </button>
              ) : (
                <button
                  onClick={() => {
                    if (lemma) statusMutation.mutate({ word: lemma, status: "new" });
                    close();
                  }}
                  className="flex-1 bg-gray-100 text-gray-700 rounded-lg py-2.5 text-sm font-medium hover:bg-gray-200 transition-colors"
                >
                  重新加入学习
                </button>
              )}
            </div>
          )}
        </motion.aside>
      )}
    </AnimatePresence>
  );
};
```

> 说明：`mastered → new` 走 `update_status` 的 `force=False` 合法转移（`VALID_TRANSITIONS["mastered"] = ["new"]`，见 `vocab_service.py`），无需 `force`。`new → mastered` 不在合法表内（`new → reviewing → mastered`），所以这里给 mastered 用 `force`？—— 见下步修正。

- [ ] **Step 2: 修正状态转移** — `new/reviewing → mastered` 需 `force`

后端 `VALID_TRANSITIONS` 只允许 `new→reviewing→mastered`，直接 `new→mastered` 会 400。侧栏「标记已掌握」要对任意未掌握状态生效，故 status 调用加 `force`。改 `statusMutation` 的 `mutationFn`：

```typescript
    mutationFn: ({ word, status }: { word: string; status: string }) =>
      api.patch(`vocab/${word}/status`, { json: { status }, searchParams: { force: "true" } }),
```

- [ ] **Step 3: 验证 —— 构建通过**

Run: `cd frontend && npm run build`
Expected: 编译通过

- [ ] **Step 4: 验证 —— 侧栏行为（运行 app）**

人工核对：
1. 点击已翻译的词 → 侧栏显示中文词义 + 英文释义 + 「你点过的位置」列表。
2. 点击某个位置链接 → 跳到对应文章并滚动到该句。
3. 「标记已掌握」→ 该词正文高亮消失（mastered 不高亮）。
4. 对 mastered 词打开侧栏 → 显示「重新加入学习」。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/WordSidebar.tsx
git commit -m "$(printf 'feat: sidebar shows dictionary meaning + click locations\n\nAlways show Chinese meaning + definitions; list recent click positions\nwith jump-to-sentence links; mastered toggle via forced transition.\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## Task 10: `VocabListPage` —— 展示词典中文义 + 状态（去掉 unseen 噪音）

**Files:**
- Modify: `frontend/src/pages/VocabListPage.tsx`

**Interfaces:**
- Consumes: `GET /vocab` → `VocabItem[]`（`context_translation` 现为词典级中文义）；侧栏（Task 9）承接位置链接与释义。
- Produces: 列表每行展示 词 + 中文义 + 状态徽标 + 状态选择器；点击行打开侧栏（含位置链接）。文案与现有一致；**位置链接不在列表内联展示，统一在侧栏**（避免列表页 N 次词典查询）。

- [ ] **Step 1: 调整列表项文案**

`VocabListPage` 当前已展示 `item.context_translation` 与状态徽标、状态选择器，点击行 `openSidebar(item.word, item.word, "", item.context_translation ?? "")`。在新模型下 `context_translation` 即词典中文义，行为已正确。仅做一处文案微调：把无中文义时的占位补上，改 `{item.context_translation && (...)}` 块为：

```tsx
                <p className="text-sm text-gray-500 mt-0.5 truncate">
                  {item.context_translation ?? "打开查看释义"}
                </p>
```

(移除原先的 `{item.context_translation && (` 条件包裹，使无义时也显示提示。)

- [ ] **Step 2: 验证 —— 构建通过**

Run: `cd frontend && npm run build`
Expected: 编译通过

- [ ] **Step 3: 验证 —— 列表与侧栏联动（运行 app）**

人工核对：
1. 生词表每行显示 词 + 中文义（或「打开查看释义」）+ 状态。
2. 点击行 → 侧栏打开，含中文义 / 英文释义 / 位置链接。
3. 行内状态选择器改状态 → 列表刷新、正文高亮随之变化（mastered 后该词正文不再高亮）。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/pages/VocabListPage.tsx
git commit -m "$(printf 'feat: vocab list shows dictionary meaning, links via sidebar\n\nShow word-level Chinese meaning (or open-to-view hint); click locations\nlive in the sidebar to avoid per-row dictionary lookups.\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## Final Verification

- [ ] **后端全测试**

Run: `cd backend && .venv/bin/python -m pytest tests/ -v`
Expected: 全部 PASS（含既有 test_translation_recovery、test_library_books、test_batch_translation_keys、test_roles、test_admin_schemas + 新增 test_position_annotations、test_edit_fallback、test_vocab_locations）

- [ ] **前端构建**

Run: `cd frontend && npm run build`
Expected: 编译通过，无类型错误

- [ ] **端到端人工验收**（运行中的 app，对照 spec 验收要点）
  1. 点击 "bank" 第 3 处：仅第 3 处显示译文；全文所有 "bank" 显示生词高亮；刷新后第 3 处译文仍在。
  2. 点同一词不同句：各按本句翻译，互不覆盖。
  3. mastered 的词：正文无高亮。
  4. 编辑文章打乱位置：旧位置标注不在错误的词上显示译文；生词高亮仍在；重新点击按新句翻译。
  5. 单词表：展示中文义 + 侧栏含英文释义 + 最近 3 处位置链接；编辑失效链接有「(原文已修改)」降级。
  6. 上传新文章 / 打开 library 文章：不再发生一个生词被预翻译进所有文章（后台无对应任务、library 打开无新 pending）。

---

## Notes / 决策记录（与 mockup 的差异）

- **位置链接放在侧栏，不内联到单词表每一行**：列表内联展示英文释义/链接会触发逐行词典 API 调用（dictionaryapi.dev 有速率限制）。改为点击行打开侧栏统一展示，符合 mm1（单词表是辅助）。如需列表内联，作为后续增强（一次性聚合查询）。
- **单词表英文释义在侧栏展开**（mockup 在列表行内 `<details>`），同上原因。
- **中文词义来源**：用 `free_translation_service`（Google 翻译，非 AI token），首次点击时种入 `vocab.context_translation`，侧栏打开时懒补。新词在被点击/打开前列表显示「打开查看释义」。
- **编辑失效仅覆盖 `edit_article`（用户自有文章）路径**；admin 编辑 library 文章重新 tokenize 的失效校验为后续增强（`revalidate_article_annotations` 已不按 user 过滤，可直接复用）。
- **`gen_status` 列保留**但恒为 `"done"`（不再有 pending 预翻译），仅为类型兼容，未来可移除。
