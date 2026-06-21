# 译文显隐随状态派生 + 「未收录」清理修复 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让单词头顶译文的显隐由收录状态派生（仅「新词」显示），把「隐藏译文」实现为 `new ⇄ reviewing` 开关，并修复「未收录」遗留位置标注导致词“按不下去”的 bug。

**Architecture:** 后端在删除 `Vocabulary` 时连带删除该词所有 `ArticleAnnotation`（按 lemma 匹配）。前端 `WordToken` 的译文显隐改用 `!!annotation?.translation && status === "new"`，点击行为改由 status 分叉（unseen→翻译收录，其余→开侧边栏）；`WordSidebar` 底部按 status 渲染「隐藏译文 / 显示译文 / 标记已掌握 / 重新加入学习」。

**Tech Stack:** 后端 FastAPI + async SQLAlchemy + pytest（跑在 dockerized Postgres，每个测试自播种自清理）；前端 React + Zustand + TanStack Query + Tailwind（无前端测试框架，前端改动靠手动验证）。

## Global Constraints

- 后端统一 async/await 风格（`async def` + `await db.scalars(...)`）。
- `ArticleAnnotation.word` 字段存的是 **lemma**；`DELETE /vocab/{word}` 路径参数 `word` 也是 lemma —— 两者按相等匹配。
- 后端测试约定：连 `settings.database_url`，用 `uuid4()` 字符串作 `user_id`/`article_id`（VARCHAR(36)，**不要加前缀**否则溢出），测试结束在 `finally` 里 `delete` 清理自己的行。
- `statusMutation` 调 `PATCH vocab/{word}/status` 时必须带 `searchParams: { force: "true" }`，否则会被状态机 `VALID_TRANSITIONS` 拦截。
- 译文按位置（per-instance）存储，前端无法按 lemma 清理内存标注；「未收录」依赖后端删除 + 文章 query 重新拉取来生效。

---

### Task 1: 后端按词删除标注 + 「未收录」清理

**Files:**
- Modify: `backend/app/services/annotation_service.py`（在文件末尾新增 `delete_word_annotations`）
- Modify: `backend/app/routers/vocab.py:42-52`（`delete_vocab` 内调用新函数）
- Test: `backend/tests/test_uncollect_cleanup.py`（新建）

**Interfaces:**
- Consumes: `ArticleAnnotation`（`app.models.annotation`）、`annotation_service.upsert_annotation`、`annotation_service.get_article_annotations`。
- Produces: `async def delete_word_annotations(db: AsyncSession, user_id: str, word: str) -> None` —— 删除某用户某 lemma 在所有文章的标注；**不** commit（调用方负责）。

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_uncollect_cleanup.py`：

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

确保 docker Postgres 在跑：`docker compose up -d`
Run: `cd backend && .venv/bin/python -m pytest tests/test_uncollect_cleanup.py -v`
Expected: FAIL —— `AttributeError: module 'app.services.annotation_service' has no attribute 'delete_word_annotations'`

- [ ] **Step 3: 实现 `delete_word_annotations`**

在 `backend/app/services/annotation_service.py` 末尾追加：

```python
async def delete_word_annotations(
    db: AsyncSession, user_id: str, word: str
) -> None:
    """Delete all position annotations for a user's lemma across every article.

    Used when a word is removed from vocabulary ("uncollect") so no stale
    translation lingers in the reader. Caller commits.
    """
    rows = list(await db.scalars(
        select(ArticleAnnotation).where(
            ArticleAnnotation.user_id == user_id,
            ArticleAnnotation.word == word,
        )
    ))
    for ann in rows:
        await db.delete(ann)
```

（`select` 已在文件顶部导入，无需新增 import。）

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/test_uncollect_cleanup.py -v`
Expected: PASS

- [ ] **Step 5: 在 `delete_vocab` 路由里接线**

修改 `backend/app/routers/vocab.py` 的 `delete_vocab`（当前 42-52 行），在删除 vocab 前清理标注：

```python
@router.delete("/vocab/{word}", status_code=204)
async def delete_vocab(
    word: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    vocab = await vocab_service.get_word(db, current_user.id, word)
    if not vocab:
        raise HTTPException(status_code=404, detail="Word not found in vocabulary")
    await annotation_service.delete_word_annotations(db, current_user.id, word)
    await db.delete(vocab)
    await db.commit()
```

（`annotation_service` 已在 `vocab.py:8` 导入，无需新增 import。）

- [ ] **Step 6: 跑整个后端测试套件，确认无回归**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: 全部 PASS（含已有 8 个测试文件 + 新增的）

- [ ] **Step 7: 提交**

```bash
git add backend/app/services/annotation_service.py backend/app/routers/vocab.py backend/tests/test_uncollect_cleanup.py
git commit -m "fix: clear position annotations when a word is uncollected

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: 前端译文显隐 + 点击行为改由状态驱动

**Files:**
- Modify: `frontend/src/components/WordToken.tsx`

**Interfaces:**
- Consumes: `useVocabStore` 的 `getStatus(lemma) -> WordStatus`、`getAnnotation(...)`、`setWordStatus`、`setAnnotation`；`useSidebarStore` 的 `open`。
- Produces: 无新导出；仅改变 `WordToken` 内部 `showTranslation` 计算与 `handleClick` 分支。

无前端测试框架，本任务靠手动验证（见 Step 3）。

- [ ] **Step 1: 修改 `showTranslation` 与点击逻辑**

在 `frontend/src/components/WordToken.tsx` 中：

将第 68 行
```tsx
  const showTranslation = !!annotation?.translation;
```
改为
```tsx
  // 译文头顶显示 = 该位置有标注 且 词处于「新词」。巩固中/已习得隐藏译文（自测）。
  const showTranslation = !!annotation?.translation && status === "new";
```

将 `handleClick`（当前 72-83 行）改为按 status 分叉，不再看 `showTranslation`：
```tsx
  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (status === "unseen") {
      // 首次：翻译并收录为「新词」
      translateMutation.mutate();
      if (autoOpenSidebar) {
        openSidebar(token.text, token.lemma, articleId, getSentenceText());
      }
    } else {
      // 已收录（new/reviewing/mastered）：打开侧边栏管理 / 自测
      openSidebar(token.text, token.lemma, articleId, getSentenceText());
    }
  };
```

（`aria-label` 第 105-107 行无需改动：它已引用 `showTranslation`，会自动跟随新公式。）

- [ ] **Step 2: 启动前后端**

```bash
docker compose up -d
cd backend && .venv/bin/uvicorn app.main:app --reload   # 终端 A
cd frontend && npm run dev                               # 终端 B
```

- [ ] **Step 3: 手动验证点击与译文显隐**

在浏览器中：
1. 打开一篇文章，点一个未收录的词 → 译文出现在头顶、词高亮（status=new）。✅
2. 刷新页面 → 该位置译文仍显示（new + 有标注）。✅
3. （为下一任务铺垫）此时还没有改 status 的 UI 入口，先确认 new 行为正常即可。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/components/WordToken.tsx
git commit -m "feat: derive head-of-word translation visibility from word status

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: 侧边栏「隐藏译文 / 显示译文」开关

**Files:**
- Modify: `frontend/src/components/WordSidebar.tsx:166-191`（底部 status 操作区）

**Interfaces:**
- Consumes: Task 2 的 `WordToken` 已让 `status==="new"` 才显示译文，故 `new→reviewing` 会隐藏译文、`reviewing→new` 会恢复；`statusMutation`（已存在）调 `PATCH vocab/{word}/status?force=true`，成功后 `setWordStatus` + 失效 `vocab`/`vocab-detail` 查询；`detail.status` 来自 `vocab/{lemma}/detail`。
- Produces: 无新导出；仅扩展底部按钮分支。

无前端测试框架，本任务靠手动验证。

- [ ] **Step 1: 重写底部操作区**

把 `frontend/src/components/WordSidebar.tsx` 当前底部块（166-191 行，即从 `{/* Status actions — pinned to bottom */}` 到对应的 `)}`）整体替换为：

```tsx
          {/* Status actions — pinned to bottom */}
          {detail && detail.status !== "unseen" && (
            <div className="p-5 border-t border-gray-100 flex gap-2">
              {detail.status === "new" && (
                <button
                  onClick={() => {
                    if (lemma) statusMutation.mutate({ word: lemma, status: "reviewing" });
                    close();
                  }}
                  className="flex-1 bg-gray-100 text-gray-700 rounded-lg py-2.5 text-sm font-medium hover:bg-gray-200 transition-colors"
                >
                  隐藏译文
                </button>
              )}
              {detail.status === "reviewing" && (
                <button
                  onClick={() => {
                    if (lemma) statusMutation.mutate({ word: lemma, status: "new" });
                    close();
                  }}
                  className="flex-1 bg-gray-100 text-gray-700 rounded-lg py-2.5 text-sm font-medium hover:bg-gray-200 transition-colors"
                >
                  显示译文
                </button>
              )}
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
```

说明：`new` 时左侧出现「隐藏译文」+ 右侧「标记已掌握」；`reviewing` 时左侧「显示译文」+ 右侧「标记已掌握」；`mastered` 时只有「重新加入学习」。

- [ ] **Step 2: 手动验证完整闭环**

前后端仍在运行（Task 2 Step 2）。在浏览器中：
1. 点一个未收录词 → 译文出现（new）。✅
2. 点该词打开侧边栏 → 看到「隐藏译文」「标记已掌握」。点「隐藏译文」→ 侧边栏关闭、头顶译文消失、下划线高亮仍在（reviewing）。✅
3. 再点该词打开侧边栏 → 看到「显示译文」。点它 → 译文恢复（new）。✅
4. 巩固中状态下，在**未点过**的另一处出现的同一个词点击 → 不贴译文、直接开侧边栏（自测）。✅
5. 点「标记已掌握」→ 高亮消失、译文隐藏（mastered）；侧边栏出现「重新加入学习」。✅

- [ ] **Step 3: 验证 bug 修复（端到端）**

1. 点一个词收录为 new、译文出现。
2. 去「生词表」页，把该词下拉选「未收录」。
3. 回到文章（导航回去或刷新）→ 该词译文消失、高亮消失。✅
4. 再点该词 → 重新翻译、重新收录为 new、译文重新出现（不再“按不下去”）。✅

- [ ] **Step 4: 提交**

```bash
git add frontend/src/components/WordSidebar.tsx
git commit -m "feat: sidebar hide/show translation toggles new<->reviewing

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage:**
- 问题1 bug（未收录清理）→ Task 1（后端删标注）+ Task 2（点击改 status 驱动，双保险）+ Task 3 Step 3（端到端验证）。✅
- 问题2 译文随状态派生（`showTranslation = !!annotation && status==="new"`）→ Task 2。✅
- 「隐藏译文」=`new→reviewing`、「显示译文」=`reviewing→new` → Task 3。✅
- 巩固中点新位置开侧边栏不贴译文 → Task 2 的 `handleClick`（非 unseen 一律开侧边栏）+ Task 3 Step 2.4 验证。✅
- 高亮不区分 new/reviewing（YAGNI）→ 未改 `VOCAB_HIGHLIGHT`/`highlighted`，符合 spec。✅
- 已习得 mastered 无高亮无译文可重新加入 → 现有逻辑保留，Task 3 Step 2.5 验证。✅

**2. Placeholder scan:** 无 TBD/TODO；每个代码步骤都给了完整代码块；测试用例为完整可运行代码。✅

**3. Type consistency:** `delete_word_annotations(db, user_id, word)` 在 Task 1 定义并在同任务路由中以相同签名调用；`statusMutation.mutate({ word, status })` 与现有 `WordSidebar` 中签名一致；status 取值 `"new"|"reviewing"|"mastered"|"unseen"` 与 `WordStatus` 类型一致。✅

**关于巩固中“记录位置”的取舍：** spec 写明巩固中点新位置不发翻译请求、不记录 location。Task 2 的 `handleClick` 对非 unseen 词一律只 `openSidebar`、不 `translateMutation.mutate()`，因此巩固中点击不会写新 annotation —— 与 spec 一致。✅
