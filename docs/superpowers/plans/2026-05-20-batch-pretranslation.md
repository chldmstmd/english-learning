# Batch Pre-Translation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pre-translate all words in an article at ingestion time, storing results in a shared cache so users get instant translations on click.

**Architecture:** New `article_translations` table stores per-position translations. A background service calls Gemini with the full article text and writes all translations at once. The `translate-word` endpoint checks this cache first; cache miss falls back to existing real-time AI translation.

**Tech Stack:** FastAPI, SQLAlchemy (async), Gemini 2.5 Flash (google-genai SDK), PostgreSQL, React + TanStack Query

---

## File Structure

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `backend/app/models/article_translation.py` | ORM model for article_translations table |
| Create | `backend/app/services/batch_translation_service.py` | Batch translation logic: build prompt, call Gemini, parse response, write DB |
| Modify | `backend/app/models/article.py` | Add `translation_status` field |
| Modify | `backend/app/routers/translate.py` | Check cache before calling AI |
| Modify | `backend/app/routers/articles.py` | Trigger batch translation on user article creation |
| Modify | `backend/app/services/voa_service.py` | Trigger batch translation on VOA article ingestion |
| Modify | `backend/app/services/ai_service.py` | Add `batch_translate_article` function |
| Modify | `backend/app/main.py` | Import new model so create_all picks it up |
| Modify | `backend/requirements.txt` | Add `google-genai` package |
| Modify | `frontend/src/types/index.ts` | Add `translation_status` to ArticleDetail type |
| Modify | `frontend/src/pages/ArticleReaderPage.tsx` | Show status banner when translation is processing |

---

### Task 1: Add `article_translations` ORM model

**Files:**
- Create: `backend/app/models/article_translation.py`
- Modify: `backend/app/main.py` (add import)

- [ ] **Step 1: Create the model file**

```python
# backend/app/models/article_translation.py
from sqlalchemy import String, Text, Integer, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ArticleTranslation(Base):
    __tablename__ = "article_translations"
    __table_args__ = (
        UniqueConstraint("article_id", "sentence_index", "word_index", name="uq_article_word_position"),
        Index("ix_article_translations_article_id", "article_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[str] = mapped_column(String(36), nullable=False)
    sentence_index: Mapped[int] = mapped_column(Integer, nullable=False)
    word_index: Mapped[int] = mapped_column(Integer, nullable=False)
    word: Mapped[str] = mapped_column(String(100), nullable=False)
    lemma: Mapped[str] = mapped_column(String(100), nullable=False)
    translation: Mapped[str] = mapped_column(Text, nullable=False)
```

- [ ] **Step 2: Register model in main.py**

Add this line in the lifespan function's import block:

```python
import app.models.article_translation  # noqa: F401
```

- [ ] **Step 3: Verify table creation**

Run: restart backend (auto-reload), then check logs for no errors.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/article_translation.py backend/app/main.py
git commit -m "feat: add article_translations model"
```

---

### Task 2: Add `translation_status` field to Article model

**Files:**
- Modify: `backend/app/models/article.py`

- [ ] **Step 1: Add the field**

Add after the `cover_image_url` field at line 38:

```python
    # Batch translation status: pending | processing | done | failed
    translation_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="pending"
    )
```

- [ ] **Step 2: Verify**

Restart backend, confirm no errors. The column will be auto-created by `create_all`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/article.py
git commit -m "feat: add translation_status field to Article model"
```

---

### Task 3: Add `batch_translate_article` to ai_service

**Files:**
- Modify: `backend/app/services/ai_service.py`

- [ ] **Step 1: Add batch config and prompt**

Add after the existing `_ANALYSIS_CONFIG`:

```python
_BATCH_TRANSLATION_CONFIG = types.GenerateContentConfig(
    thinking_config=types.ThinkingConfig(thinking_budget=0),
    response_mime_type="application/json",
    max_output_tokens=16000,
    temperature=0.1,
)

_BATCH_TRANSLATION_PROMPT = (
    "你是专业英中词汇翻译助手。\n"
    "下面是一篇英文文章，以及文章中每个单词的位置信息。\n"
    "请根据上下文，为每个单词提供最符合语境的中文翻译（2-6个中文字）。\n"
    "对于虚词（the, a, is, are, was, were, be, to, of, in, on, at, for, and, or, but, "
    "that, this, it, not, no, do, does, did, have, has, had, will, would, can, could, "
    "shall, should, may, might, must）翻译为空字符串。\n\n"
    "返回JSON数组，每项格式：{{\"si\": 句子序号, \"wi\": 词序号, \"t\": \"翻译\"}}\n"
    "严格按照输入的位置列表顺序返回，不要遗漏任何一项。\n\n"
    "文章全文：\n{article_text}\n\n"
    "单词位置列表：\n{word_list}"
)
```

- [ ] **Step 2: Add the batch function**

```python
async def batch_translate_article(article_text: str, words: list[dict]) -> list[dict]:
    """
    Translate all words in an article at once.
    words: [{"si": sentence_index, "wi": word_index, "w": word}]
    Returns: [{"si": int, "wi": int, "t": str}]
    """
    word_list_str = json.dumps(words, ensure_ascii=False)
    prompt = _BATCH_TRANSLATION_PROMPT.format(
        article_text=article_text, word_list=word_list_str
    )
    response = await asyncio.wait_for(
        _client.aio.models.generate_content(
            model=_MODEL, contents=prompt, config=_BATCH_TRANSLATION_CONFIG
        ),
        timeout=60.0,
    )
    result = json.loads(response.text)
    return result
```

- [ ] **Step 3: Quick manual test**

```bash
cd backend && .venv/bin/python -c "
import asyncio, json
from app.services.ai_service import batch_translate_article

async def test():
    text = 'The cat sat on the mat. It was a sunny day.'
    words = [
        {'si': 0, 'wi': 0, 'w': 'The'},
        {'si': 0, 'wi': 1, 'w': 'cat'},
        {'si': 0, 'wi': 2, 'w': 'sat'},
        {'si': 0, 'wi': 3, 'w': 'on'},
        {'si': 0, 'wi': 4, 'w': 'the'},
        {'si': 0, 'wi': 5, 'w': 'mat'},
        {'si': 1, 'wi': 0, 'w': 'It'},
        {'si': 1, 'wi': 1, 'w': 'was'},
        {'si': 1, 'wi': 2, 'w': 'a'},
        {'si': 1, 'wi': 3, 'w': 'sunny'},
        {'si': 1, 'wi': 4, 'w': 'day'},
    ]
    result = await batch_translate_article(text, words)
    print(json.dumps(result, ensure_ascii=False, indent=2))

asyncio.run(test())
"
```

Expected: JSON array with translations, function words have empty string `"t": ""`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/ai_service.py
git commit -m "feat: add batch_translate_article function to ai_service"
```

---

### Task 4: Create batch_translation_service

**Files:**
- Create: `backend/app/services/batch_translation_service.py`

- [ ] **Step 1: Create the service**

```python
# backend/app/services/batch_translation_service.py
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.article import Article
from app.models.article_translation import ArticleTranslation
from app.services import ai_service

logger = logging.getLogger(__name__)


async def translate_article(article_id: str) -> None:
    """
    Batch-translate all alpha words in an article and store results.
    Intended to be called as a background task.
    """
    async with AsyncSessionLocal() as db:
        article = await db.scalar(
            select(Article).where(Article.id == article_id)
        )
        if not article:
            logger.error("Article %s not found for batch translation", article_id)
            return

        article.translation_status = "processing"
        await db.commit()

        try:
            # Build word list from tokens
            words = []
            for token in article.tokens:
                if token["is_alpha"]:
                    words.append({
                        "si": token["sentence_index"],
                        "wi": token["index"],
                        "w": token["text"],
                    })

            if not words:
                article.translation_status = "done"
                await db.commit()
                return

            # Call AI
            translations = await ai_service.batch_translate_article(
                article.raw_text, words
            )

            # Build lookup from AI response
            trans_map = {(item["si"], item["wi"]): item["t"] for item in translations}

            # Write to DB
            records = []
            for word_info in words:
                key = (word_info["si"], word_info["wi"])
                translation = trans_map.get(key, "")
                # Find lemma from tokens
                lemma = ""
                for token in article.tokens:
                    if token["index"] == word_info["wi"] and token["sentence_index"] == word_info["si"]:
                        lemma = token["lemma"]
                        break
                records.append(ArticleTranslation(
                    article_id=article_id,
                    sentence_index=word_info["si"],
                    word_index=word_info["wi"],
                    word=word_info["w"],
                    lemma=lemma,
                    translation=translation,
                ))

            db.add_all(records)
            article.translation_status = "done"
            await db.commit()
            logger.info("Batch translation complete for article %s (%d words)", article_id, len(records))

        except Exception as exc:
            logger.error("Batch translation failed for article %s: %s", article_id, exc)
            await db.rollback()
            # Re-fetch to update status
            async with AsyncSessionLocal() as db2:
                article = await db2.scalar(select(Article).where(Article.id == article_id))
                if article:
                    article.translation_status = "failed"
                    await db2.commit()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/batch_translation_service.py
git commit -m "feat: add batch_translation_service for background article translation"
```

---

### Task 5: Trigger batch translation on article creation

**Files:**
- Modify: `backend/app/routers/articles.py`
- Modify: `backend/app/services/voa_service.py`

- [ ] **Step 1: Trigger in user article creation (articles.py)**

Add import at top:

```python
from app.services import batch_translation_service
import asyncio
```

In `create_article`, after `await db.commit()` (line 46), before the return, add:

```python
    asyncio.create_task(batch_translation_service.translate_article(article.id))
```

- [ ] **Step 2: Trigger in VOA sync (voa_service.py)**

Add import at top:

```python
from app.services import batch_translation_service
```

In `sync_feed`, after `await db.commit()` at line 257 (inside the try block after adding the article), add:

```python
            asyncio.create_task(batch_translation_service.translate_article(article.id))
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/articles.py backend/app/services/voa_service.py
git commit -m "feat: trigger batch translation on article creation and VOA sync"
```

---

### Task 6: Modify translate-word to check cache first

**Files:**
- Modify: `backend/app/routers/translate.py`
- Modify: `backend/app/schemas/translate.py`

- [ ] **Step 1: Update TranslateRequest schema**

Add `sentence_index` and `word_index` fields to `TranslateRequest` in `schemas/translate.py`:

```python
class TranslateRequest(BaseModel):
    word: str    # surface form (e.g. "banks")
    lemma: str   # lowercase lemma used as vocab key (e.g. "bank")
    sentence: str
    article_id: str
    sentence_index: int | None = None  # for cache lookup
    word_index: int | None = None      # for cache lookup
```

- [ ] **Step 2: Add cache lookup in translate router**

In `backend/app/routers/translate.py`, add import:

```python
from app.models.article_translation import ArticleTranslation
```

In `translate_word`, after the article lookup (line 46-48 area), before calling `_get_translation_with_fallback`, add cache check:

```python
    # Check batch translation cache
    cached_translation = None
    if body.sentence_index is not None and body.word_index is not None:
        cached = await db.scalar(
            select(ArticleTranslation).where(
                ArticleTranslation.article_id == body.article_id,
                ArticleTranslation.sentence_index == body.sentence_index,
                ArticleTranslation.word_index == body.word_index,
            )
        )
        if cached and cached.translation:
            cached_translation = cached.translation
```

Then replace the call to `_get_translation_with_fallback` with:

```python
    if cached_translation:
        translation, is_fallback = cached_translation, False
    else:
        translation, is_fallback = await _get_translation_with_fallback(body.lemma, body.sentence)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/translate.py backend/app/schemas/translate.py
git commit -m "feat: check batch translation cache in translate-word endpoint"
```

---

### Task 7: Update frontend to send position info and show status

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/components/WordToken.tsx`
- Modify: `frontend/src/pages/ArticleReaderPage.tsx`

- [ ] **Step 1: Update types**

Add `translation_status` to the `ArticleDetail` type in `frontend/src/types/index.ts`:

```typescript
// Add to ArticleDetail interface:
translation_status?: string;  // "pending" | "processing" | "done" | "failed"
```

- [ ] **Step 2: Send position info in WordToken click**

In `frontend/src/components/WordToken.tsx`, update the `mutationFn` in `translateMutation` to include position:

```typescript
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
```

- [ ] **Step 3: Show translation status banner in ArticleReaderPage**

In `frontend/src/pages/ArticleReaderPage.tsx`, add a banner after the top bar when translation is processing:

```tsx
{article.translation_status === "processing" && (
  <div className="bg-blue-50 text-blue-600 text-xs text-center py-1.5">
    正在准备翻译缓存...
  </div>
)}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/components/WordToken.tsx frontend/src/pages/ArticleReaderPage.tsx
git commit -m "feat: frontend sends word position, shows translation status"
```

---

### Task 8: Update requirements.txt and expose translation_status in API response

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/app/schemas/article.py`

- [ ] **Step 1: Add google-genai to requirements.txt**

Add line:

```
google-genai>=1.0.0
```

- [ ] **Step 2: Expose translation_status in ArticleDetailResponse**

Check `backend/app/schemas/article.py` and add `translation_status: str` to `ArticleDetailResponse`.

- [ ] **Step 3: Commit**

```bash
git add backend/requirements.txt backend/app/schemas/article.py
git commit -m "chore: add google-genai dep, expose translation_status in API"
```

---

### Task 9: End-to-end test

- [ ] **Step 1: Create a test article and verify batch translation**

```bash
# Login first
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/auth/login \
  -d "username=test@test.com&password=123456" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Create article
curl -s -X POST http://127.0.0.1:8000/api/v1/articles \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Test Batch","raw_text":"The scientists discovered a new species in the forest. They published their findings in a journal."}' | python3 -m json.tool
```

- [ ] **Step 2: Wait 5 seconds, then check translation cache**

```bash
# Check article translation_status
curl -s http://127.0.0.1:8000/api/v1/articles/<ARTICLE_ID> \
  -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; d=json.load(sys.stdin); print('status:', d.get('translation_status'))"
```

- [ ] **Step 3: Test translate-word with cache hit**

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/translate-word \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"word":"discovered","lemma":"discover","sentence":"The scientists discovered a new species in the forest.","article_id":"<ARTICLE_ID>","sentence_index":0,"word_index":2}' | python3 -m json.tool
```

Expected: fast response with `is_fallback: false`, translation from cache.

- [ ] **Step 4: Commit final state if any fixes needed**

```bash
git add -A && git commit -m "fix: end-to-end test fixes for batch translation"
```
