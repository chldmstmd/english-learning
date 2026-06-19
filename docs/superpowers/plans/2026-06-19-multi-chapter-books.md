# Multi-Chapter Books & Reading Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Book" container so users can read multi-chapter long-form content (起点中文网-style: a book holds many chapters, each chapter is a regular article), and remember where they left off (which chapter + which sentence).

**Architecture:** A new `books` table holds book metadata. The existing `articles` table gains `book_id` + `chapter_order` so a chapter is just a normal article that belongs to a book. The existing `user_reading_history` table gains `book_id` + `last_sentence_index` for resume position. Chapter creation reuses the existing article creation pipeline (tokenize → translation cache → vocab annotations) verbatim. Independent articles (`book_id = null`) are unchanged.

**Tech Stack:** FastAPI + async SQLAlchemy + PostgreSQL (backend); React + TanStack Query + Zustand + Tailwind (frontend). No test framework exists in this project — verification is done by running the app and exercising endpoints with `curl` (backend) and the browser (frontend), matching the established project convention.

---

## Verification Conventions

This project has **no pytest / vitest**. Every task is verified by:
- **Backend:** restart uvicorn, then hit the endpoint with `curl` and inspect the JSON. A reusable login snippet is provided below.
- **Frontend:** load the page in the browser at `http://localhost:5173` and exercise the flow.

**Reusable backend setup** (run from `backend/` with the venv active; the dev server must be running on port 8000):

```bash
# Obtain a token for the existing test user (created during setup)
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/auth/login \
  -d "username=test@example.com&password=test1234" \
  | .venv/bin/python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "token len: ${#TOKEN}"   # expect ~165
```

`create_all` runs on startup and **only creates missing tables / it does NOT alter existing ones**. Tasks that add columns to existing tables (`articles`, `user_reading_history`) therefore include an explicit `ALTER TABLE` step against the running Postgres (container `english_learning_db`). New tables (`books`) are created automatically by `create_all`.

Postgres exec helper used in several tasks:

```bash
docker exec -i english_learning_db psql -U postgres -d english_learning -c "<SQL>"
```

---

## File Structure

**Backend — create:**
- `backend/app/models/book.py` — `Book` ORM model
- `backend/app/schemas/book.py` — Pydantic request/response models for books & chapters
- `backend/app/routers/books.py` — book CRUD + add-chapter + book detail

**Backend — modify:**
- `backend/app/models/article.py` — add `book_id`, `chapter_order`
- `backend/app/models/reading_history.py` — add `book_id`, `last_sentence_index`
- `backend/app/schemas/article.py` — add `book_id`/`chapter_order` to `ArticleDetailResponse`; add `ChapterEditRequest`, `ProgressUpdateRequest`
- `backend/app/routers/articles.py` — add `PUT /articles/{id}` (edit chapter), `PUT /articles/{id}/progress`; include `book_id`/`chapter_order` + prev/next in detail response
- `backend/app/main.py` — register `book.py` model import + `books` router

**Frontend — create:**
- `frontend/src/pages/BookDetailPage.tsx` — chapter list + "continue reading" + "add chapter"
- `frontend/src/components/CreateBookForm.tsx` — create-book form (used on list page)

**Frontend — modify:**
- `frontend/src/types/index.ts` — add `Book`, `BookListItem`, `BookDetail`, `Chapter` types; extend `ArticleDetail`
- `frontend/src/App.tsx` — add `/books/:id` route
- `frontend/src/pages/ArticleListPage.tsx` — merge books + articles into one list; add "create book" entry
- `frontend/src/pages/ArticleReaderPage.tsx` — prev/next chapter nav; record/restore `last_sentence_index`

---

## Task 1: Add `Book` model + `books` table

**Files:**
- Create: `backend/app/models/book.py`
- Modify: `backend/app/main.py:36` (add model import in `lifespan`)

- [ ] **Step 1: Create the Book model**

Create `backend/app/models/book.py`:

```python
from datetime import datetime
from uuid import uuid4

from sqlalchemy import String, Text, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Book(Base):
    __tablename__ = "books"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    cover_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # is_library=True reserved for future admin-managed public books
    is_library: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 2: Register the model import so create_all builds the table**

In `backend/app/main.py`, inside `lifespan`, add the import alongside the others (after line 36 `import app.models.article_translation`):

```python
    import app.models.book                # noqa: F401
```

- [ ] **Step 3: Restart the backend and verify the table was created**

Restart uvicorn (stop the running process, then from `backend/`):

```bash
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then in another shell:

```bash
docker exec -i english_learning_db psql -U postgres -d english_learning -c "\d books"
```

Expected: table description listing columns `id, user_id, title, cover_image_url, source_category, is_library, created_at`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/book.py backend/app/main.py
git commit -m "feat: add Book model and books table"
```

---

## Task 2: Add `book_id` + `chapter_order` to articles

**Files:**
- Modify: `backend/app/models/article.py:38` (after `cover_image_url`)

- [ ] **Step 1: Add the columns to the Article model**

In `backend/app/models/article.py`, add after the `translation_status` column (line 40-42):

```python
    # V1.2: Book/chapter fields (null for standalone articles)
    book_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    chapter_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

(`Integer` and `String` are already imported at the top of the file.)

- [ ] **Step 2: ALTER the existing table (create_all won't add columns)**

```bash
docker exec -i english_learning_db psql -U postgres -d english_learning -c "ALTER TABLE articles ADD COLUMN IF NOT EXISTS book_id VARCHAR(36), ADD COLUMN IF NOT EXISTS chapter_order INTEGER; CREATE INDEX IF NOT EXISTS ix_articles_book_id ON articles (book_id);"
```

Expected: `ALTER TABLE` then `CREATE INDEX` success messages.

- [ ] **Step 3: Restart backend and verify columns exist**

Restart uvicorn, then:

```bash
docker exec -i english_learning_db psql -U postgres -d english_learning -c "\d articles" | grep -E "book_id|chapter_order"
```

Expected: two rows showing `book_id | character varying(36)` and `chapter_order | integer`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/article.py
git commit -m "feat: add book_id and chapter_order to articles"
```

---

## Task 3: Add `book_id` + `last_sentence_index` to reading history

**Files:**
- Modify: `backend/app/models/reading_history.py:17` (after existing columns)

- [ ] **Step 1: Add the columns to the model**

In `backend/app/models/reading_history.py`, add `Integer` to the sqlalchemy import line, then add the columns after `last_read_at`:

```python
from sqlalchemy import String, DateTime, Integer, UniqueConstraint, func
```

```python
    book_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    last_sentence_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

- [ ] **Step 2: ALTER the existing table**

```bash
docker exec -i english_learning_db psql -U postgres -d english_learning -c "ALTER TABLE user_reading_history ADD COLUMN IF NOT EXISTS book_id VARCHAR(36), ADD COLUMN IF NOT EXISTS last_sentence_index INTEGER; CREATE INDEX IF NOT EXISTS ix_urh_book_id ON user_reading_history (book_id);"
```

Expected: `ALTER TABLE` and `CREATE INDEX` success.

- [ ] **Step 3: Restart backend and verify**

```bash
docker exec -i english_learning_db psql -U postgres -d english_learning -c "\d user_reading_history" | grep -E "book_id|last_sentence_index"
```

Expected: two rows for the new columns.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/reading_history.py
git commit -m "feat: add book_id and last_sentence_index to reading history"
```

---

## Task 4: Book schemas

**Files:**
- Create: `backend/app/schemas/book.py`

- [ ] **Step 1: Create the schemas file**

Create `backend/app/schemas/book.py`:

```python
from datetime import datetime

from pydantic import BaseModel


class BookCreateRequest(BaseModel):
    title: str
    cover_image_url: str | None = None
    source_category: str | None = None


class ChapterCreateRequest(BaseModel):
    title: str
    raw_text: str


class BookListItem(BaseModel):
    id: str
    title: str
    cover_image_url: str | None
    source_category: str | None
    created_at: datetime
    chapter_count: int = 0          # populated per-request
    read_chapter_order: int | None = None   # which chapter the user last read (1-based order)

    model_config = {"from_attributes": True}


class ChapterListItem(BaseModel):
    id: str
    title: str
    chapter_order: int
    word_count: int
    last_sentence_index: int | None = None   # per-user resume position within this chapter

    model_config = {"from_attributes": True}


class BookDetailResponse(BaseModel):
    id: str
    title: str
    cover_image_url: str | None
    source_category: str | None
    created_at: datetime
    chapters: list[ChapterListItem]
    # Resume target: the chapter article_id to continue from, or null if unread
    continue_article_id: str | None = None
    continue_sentence_index: int | None = None
```

- [ ] **Step 2: Verify it imports cleanly**

From `backend/`:

```bash
.venv/bin/python -c "from app.schemas.book import BookCreateRequest, ChapterCreateRequest, BookListItem, ChapterListItem, BookDetailResponse; print('OK')"
```

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/book.py
git commit -m "feat: add book and chapter schemas"
```

---

## Task 5: Books router — create book & list books

**Files:**
- Create: `backend/app/routers/books.py`
- Modify: `backend/app/main.py` (import + include router)

- [ ] **Step 1: Create the router with create + list endpoints**

Create `backend/app/routers/books.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.article import Article
from app.models.book import Book
from app.models.reading_history import UserReadingHistory
from app.models.user import User
from app.schemas.book import BookCreateRequest, BookListItem

router = APIRouter(tags=["books"])


@router.post("/books", response_model=BookListItem, status_code=201)
async def create_book(
    body: BookCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    book = Book(
        user_id=current_user.id,
        title=body.title,
        cover_image_url=body.cover_image_url,
        source_category=body.source_category,
    )
    db.add(book)
    await db.commit()
    item = BookListItem.model_validate(book)
    item.chapter_count = 0
    return item


@router.get("/books", response_model=list[BookListItem])
async def list_books(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    books = list(await db.scalars(
        select(Book)
        .where(Book.user_id == current_user.id)
        .order_by(Book.created_at.desc())
    ))
    if not books:
        return []

    book_ids = [b.id for b in books]

    # chapter counts per book
    count_rows = await db.execute(
        select(Article.book_id, func.count(Article.id))
        .where(Article.book_id.in_(book_ids))
        .group_by(Article.book_id)
    )
    count_map = {bid: cnt for bid, cnt in count_rows.all()}

    # last-read chapter per book (max chapter_order among read chapters)
    read_rows = await db.execute(
        select(UserReadingHistory.book_id, Article.chapter_order)
        .join(Article, Article.id == UserReadingHistory.article_id)
        .where(
            UserReadingHistory.user_id == current_user.id,
            UserReadingHistory.book_id.in_(book_ids),
        )
    )
    read_map: dict[str, int] = {}
    for bid, order in read_rows.all():
        if order is not None and (bid not in read_map or order > read_map[bid]):
            read_map[bid] = order

    result = []
    for b in books:
        item = BookListItem.model_validate(b)
        item.chapter_count = count_map.get(b.id, 0)
        item.read_chapter_order = read_map.get(b.id)
        result.append(item)
    return result
```

- [ ] **Step 2: Register the router in main.py**

In `backend/app/main.py` line 60, add `books` to the import:

```python
from app.routers import articles, vocab, translate, settings, library, admin, auth, books  # noqa: E402
```

And after line 67 (`app.include_router(library.router, prefix="/api/v1")`):

```python
app.include_router(books.router, prefix="/api/v1")
```

- [ ] **Step 3: Restart backend, then verify create + list**

Restart uvicorn. Get a token (see Verification Conventions), then:

```bash
BOOK_ID=$(curl -s -X POST http://127.0.0.1:8000/api/v1/books \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"title":"Test Book"}' \
  | .venv/bin/python -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "book: $BOOK_ID"
curl -s http://127.0.0.1:8000/api/v1/books -H "Authorization: Bearer $TOKEN"
```

Expected: create returns a JSON book with `chapter_count: 0`; list returns an array containing that book with `chapter_count: 0` and `read_chapter_order: null`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/books.py backend/app/main.py
git commit -m "feat: add create-book and list-books endpoints"
```

---

## Task 6: Add-chapter endpoint (reuses article creation pipeline)

**Files:**
- Modify: `backend/app/routers/books.py` (add endpoint + imports)

- [ ] **Step 1: Add the add-chapter endpoint**

In `backend/app/routers/books.py`, add these imports at the top (alongside existing):

```python
import asyncio

from app.schemas.book import ChapterCreateRequest
from app.schemas.article import ArticleListItem
from app.services import nlp_service, vocab_service, annotation_service, batch_translation_service
```

Then add the endpoint:

```python
@router.post("/books/{book_id}/chapters", response_model=ArticleListItem, status_code=201)
async def add_chapter(
    book_id: str,
    body: ChapterCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    book = await db.scalar(
        select(Book).where(Book.id == book_id, Book.user_id == current_user.id)
    )
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    tokens, sentences, word_count = nlp_service.tokenize(body.raw_text)
    if word_count > 10000:
        raise HTTPException(status_code=400, detail="Chapter exceeds 10,000 word limit")

    # next chapter_order = current max + 1 (1-based)
    max_order = await db.scalar(
        select(func.max(Article.chapter_order)).where(Article.book_id == book_id)
    )
    next_order = (max_order or 0) + 1

    article = Article(
        user_id=current_user.id,
        title=body.title,
        raw_text=body.raw_text,
        tokens=tokens,
        sentences=sentences,
        word_count=word_count,
        book_id=book_id,
        chapter_order=next_order,
    )
    db.add(article)
    await db.flush()

    word_statuses = await vocab_service.get_all_word_statuses(db, current_user.id)
    article_lemmas = {t["lemma"] for t in tokens if t["is_alpha"]}
    for word in word_statuses:
        if word in article_lemmas:
            await annotation_service.upsert_annotation(
                db, article.id, current_user.id, word, gen_status="pending"
            )

    await db.commit()
    asyncio.create_task(batch_translation_service.translate_article(article.id))
    return ArticleListItem.model_validate(article)
```

- [ ] **Step 2: Restart backend, then add two chapters and verify ordering**

Restart uvicorn. Reuse `$TOKEN` and `$BOOK_ID` from Task 5 (re-create the book if needed):

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/books/$BOOK_ID/chapters" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"title":"Chapter One","raw_text":"The sun rose over the quiet hills. Birds began to sing."}'
echo "---"
curl -s -X POST "http://127.0.0.1:8000/api/v1/books/$BOOK_ID/chapters" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"title":"Chapter Two","raw_text":"A traveler walked along the dusty road toward town."}'
```

Verify chapter_order in DB:

```bash
docker exec -i english_learning_db psql -U postgres -d english_learning -c \
  "SELECT title, chapter_order FROM articles WHERE book_id='$BOOK_ID' ORDER BY chapter_order;"
```

Expected: `Chapter One | 1` and `Chapter Two | 2`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/books.py
git commit -m "feat: add chapter creation endpoint reusing article pipeline"
```

---

## Task 7: Book detail endpoint (chapters + resume position)

**Files:**
- Modify: `backend/app/routers/books.py` (add endpoint + import)

- [ ] **Step 1: Add the book detail endpoint**

In `backend/app/routers/books.py`, add to imports:

```python
from app.schemas.book import BookDetailResponse, ChapterListItem
```

Add the endpoint:

```python
@router.get("/books/{book_id}", response_model=BookDetailResponse)
async def get_book(
    book_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    book = await db.scalar(
        select(Book).where(Book.id == book_id, Book.user_id == current_user.id)
    )
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    chapters = list(await db.scalars(
        select(Article)
        .where(Article.book_id == book_id)
        .order_by(Article.chapter_order)
    ))

    # per-chapter resume positions
    history_rows = list(await db.scalars(
        select(UserReadingHistory).where(
            UserReadingHistory.user_id == current_user.id,
            UserReadingHistory.book_id == book_id,
        )
    ))
    resume_by_article = {h.article_id: h.last_sentence_index for h in history_rows}

    chapter_items = []
    for c in chapters:
        item = ChapterListItem.model_validate(c)
        item.last_sentence_index = resume_by_article.get(c.id)
        chapter_items.append(item)

    # continue-reading target = highest chapter_order the user has a history row for
    continue_article_id = None
    continue_sentence_index = None
    best_order = -1
    for c in chapters:
        if c.id in resume_by_article and (c.chapter_order or 0) > best_order:
            best_order = c.chapter_order or 0
            continue_article_id = c.id
            continue_sentence_index = resume_by_article[c.id]
    # if nothing read yet, default to first chapter
    if continue_article_id is None and chapters:
        continue_article_id = chapters[0].id
        continue_sentence_index = 0

    return BookDetailResponse(
        id=book.id,
        title=book.title,
        cover_image_url=book.cover_image_url,
        source_category=book.source_category,
        created_at=book.created_at,
        chapters=chapter_items,
        continue_article_id=continue_article_id,
        continue_sentence_index=continue_sentence_index,
    )
```

- [ ] **Step 2: Restart backend, then verify detail**

Restart uvicorn. Reuse `$TOKEN` and `$BOOK_ID`:

```bash
curl -s "http://127.0.0.1:8000/api/v1/books/$BOOK_ID" -H "Authorization: Bearer $TOKEN" \
  | .venv/bin/python -m json.tool
```

Expected: JSON with `chapters` array (two entries, ordered, each with `chapter_order` and `last_sentence_index: null`), `continue_article_id` = first chapter's id, `continue_sentence_index: 0`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/books.py
git commit -m "feat: add book detail endpoint with chapters and resume position"
```

---

## Task 8: Delete-book endpoint (cascade chapters)

**Files:**
- Modify: `backend/app/routers/books.py` (add endpoint)

- [ ] **Step 1: Add the delete endpoint**

In `backend/app/routers/books.py`, add:

```python
from sqlalchemy import delete as sa_delete


@router.delete("/books/{book_id}", status_code=204)
async def delete_book(
    book_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    book = await db.scalar(
        select(Book).where(Book.id == book_id, Book.user_id == current_user.id)
    )
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    # delete all chapters belonging to this book, then the book
    await db.execute(sa_delete(Article).where(Article.book_id == book_id))
    await db.delete(book)
    await db.commit()
```

- [ ] **Step 2: Restart backend, then verify cascade delete**

Restart uvicorn. Using a throwaway book:

```bash
TMP=$(curl -s -X POST http://127.0.0.1:8000/api/v1/books -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"title":"Throwaway"}' | .venv/bin/python -c "import sys,json;print(json.load(sys.stdin)['id'])")
curl -s -X POST "http://127.0.0.1:8000/api/v1/books/$TMP/chapters" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"title":"C1","raw_text":"Hello world."}' >/dev/null
curl -s -o /dev/null -w "delete status: %{http_code}\n" -X DELETE "http://127.0.0.1:8000/api/v1/books/$TMP" -H "Authorization: Bearer $TOKEN"
docker exec -i english_learning_db psql -U postgres -d english_learning -c "SELECT count(*) FROM articles WHERE book_id='$TMP';"
```

Expected: `delete status: 204` and the article count is `0`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/books.py
git commit -m "feat: add delete-book endpoint with chapter cascade"
```

---

## Task 9: Edit-chapter endpoint (re-tokenize + reset drifted progress)

**Files:**
- Modify: `backend/app/schemas/article.py` (add `ChapterEditRequest`)
- Modify: `backend/app/routers/articles.py` (add `PUT /articles/{id}`)

- [ ] **Step 1: Add the edit request schema**

In `backend/app/schemas/article.py`, add after `ArticleCreateRequest`:

```python
class ChapterEditRequest(BaseModel):
    title: str
    raw_text: str
```

- [ ] **Step 2: Add the edit endpoint**

In `backend/app/routers/articles.py`, add to the imports at the top:

```python
from app.models.reading_history import UserReadingHistory
from app.schemas.article import ChapterEditRequest
```

(Also ensure `nlp_service` and `batch_translation_service` are imported — they already are on line 13.)

Add the endpoint:

```python
@router.put("/articles/{article_id}", response_model=ArticleListItem)
async def edit_article(
    article_id: str,
    body: ChapterEditRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    article = await db.scalar(
        select(Article).where(Article.id == article_id, Article.user_id == current_user.id)
    )
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    old_sentence_count = len(article.sentences)
    tokens, sentences, word_count = nlp_service.tokenize(body.raw_text)
    if word_count > 10000:
        raise HTTPException(status_code=400, detail="Article exceeds 10,000 word limit")

    article.title = body.title
    article.raw_text = body.raw_text
    article.tokens = tokens
    article.sentences = sentences
    article.word_count = word_count
    article.translation_status = "pending"

    # If sentence count changed, the saved resume anchor is no longer valid → reset to chapter start
    if len(sentences) != old_sentence_count:
        await db.execute(
            update(UserReadingHistory)
            .where(UserReadingHistory.article_id == article_id)
            .values(last_sentence_index=0)
        )

    await db.commit()
    asyncio.create_task(batch_translation_service.translate_article(article.id))
    return ArticleListItem.model_validate(article)
```

Add `update` to the sqlalchemy import on line 2 of `articles.py`:

```python
from sqlalchemy import select, or_, update
```

- [ ] **Step 3: Restart backend, then verify edit + progress reset**

Restart uvicorn. Take an existing chapter article id (`$ART` below — grab one from the book detail call). First set a fake resume position, then edit with a different sentence count and confirm reset:

```bash
ART=$(curl -s "http://127.0.0.1:8000/api/v1/books/$BOOK_ID" -H "Authorization: Bearer $TOKEN" | .venv/bin/python -c "import sys,json; print(json.load(sys.stdin)['chapters'][0]['id'])")
# seed a reading-history row with last_sentence_index=5
docker exec -i english_learning_db psql -U postgres -d english_learning -c "INSERT INTO user_reading_history (id, user_id, article_id, book_id, last_sentence_index) SELECT gen_random_uuid()::text, user_id, id, book_id, 5 FROM articles WHERE id='$ART' ON CONFLICT (user_id, article_id) DO UPDATE SET last_sentence_index=5;"
# edit with a DIFFERENT number of sentences (3 sentences here)
curl -s -X PUT "http://127.0.0.1:8000/api/v1/articles/$ART" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"title":"Chapter One (edited)","raw_text":"One. Two. Three."}' >/dev/null
docker exec -i english_learning_db psql -U postgres -d english_learning -c "SELECT last_sentence_index FROM user_reading_history WHERE article_id='$ART';"
```

Expected: `last_sentence_index` is now `0` (was reset because sentence count changed).

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/article.py backend/app/routers/articles.py
git commit -m "feat: add chapter edit endpoint that resets drifted reading progress"
```

---

## Task 10: Progress-update endpoint + expose book fields in article detail

**Files:**
- Modify: `backend/app/schemas/article.py` (add `ProgressUpdateRequest`; extend `ArticleDetailResponse`)
- Modify: `backend/app/routers/articles.py` (add `PUT /articles/{id}/progress`; include book fields + prev/next in detail)

- [ ] **Step 1: Add the progress request schema + extend detail response**

In `backend/app/schemas/article.py`, add:

```python
class ProgressUpdateRequest(BaseModel):
    last_sentence_index: int
```

And add these fields to `ArticleDetailResponse` (after `translation_status`):

```python
    # Chapter context (null for standalone articles)
    book_id: str | None = None
    chapter_order: int | None = None
    prev_article_id: str | None = None
    next_article_id: str | None = None
    last_sentence_index: int | None = None
```

- [ ] **Step 2: Add the progress endpoint**

In `backend/app/routers/articles.py`, add to imports:

```python
from datetime import datetime, timezone
from app.schemas.article import ProgressUpdateRequest
```

Add the endpoint:

```python
@router.put("/articles/{article_id}/progress", status_code=200)
async def update_progress(
    article_id: str,
    body: ProgressUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    article = await db.scalar(select(Article).where(Article.id == article_id))
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    existing = await db.scalar(
        select(UserReadingHistory).where(
            UserReadingHistory.user_id == current_user.id,
            UserReadingHistory.article_id == article_id,
        )
    )
    if existing:
        existing.last_sentence_index = body.last_sentence_index
        existing.book_id = article.book_id
        existing.last_read_at = datetime.now(timezone.utc)
    else:
        db.add(UserReadingHistory(
            user_id=current_user.id,
            article_id=article_id,
            book_id=article.book_id,
            last_sentence_index=body.last_sentence_index,
        ))
    await db.commit()
    return {"saved": True}
```

- [ ] **Step 3: Include book fields + prev/next + resume in the detail response**

In `backend/app/routers/articles.py`, modify `get_article` (the `GET /articles/{article_id}` handler). After fetching `article` and before building the response, compute prev/next + resume:

```python
    prev_article_id = None
    next_article_id = None
    if article.book_id is not None and article.chapter_order is not None:
        prev_article_id = await db.scalar(
            select(Article.id)
            .where(Article.book_id == article.book_id, Article.chapter_order < article.chapter_order)
            .order_by(Article.chapter_order.desc())
            .limit(1)
        )
        next_article_id = await db.scalar(
            select(Article.id)
            .where(Article.book_id == article.book_id, Article.chapter_order > article.chapter_order)
            .order_by(Article.chapter_order.asc())
            .limit(1)
        )

    history = await db.scalar(
        select(UserReadingHistory).where(
            UserReadingHistory.user_id == current_user.id,
            UserReadingHistory.article_id == article_id,
        )
    )
    last_sentence_index = history.last_sentence_index if history else None
```

Then add the new fields to the `ArticleDetailResponse(...)` return:

```python
        book_id=article.book_id,
        chapter_order=article.chapter_order,
        prev_article_id=prev_article_id,
        next_article_id=next_article_id,
        last_sentence_index=last_sentence_index,
```

- [ ] **Step 4: Restart backend, then verify progress save + detail fields**

Restart uvicorn. Using `$ART` (a chapter) and `$BOOK_ID`:

```bash
curl -s -X PUT "http://127.0.0.1:8000/api/v1/articles/$ART/progress" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"last_sentence_index":2}'
echo "---detail---"
curl -s "http://127.0.0.1:8000/api/v1/articles/$ART" -H "Authorization: Bearer $TOKEN" \
  | .venv/bin/python -c "import sys,json; d=json.load(sys.stdin); print({k:d[k] for k in ['book_id','chapter_order','prev_article_id','next_article_id','last_sentence_index']})"
```

Expected: progress returns `{"saved": true}`; detail shows `book_id` set, `chapter_order: 1`, `prev_article_id: None`, `next_article_id` = chapter two's id, `last_sentence_index: 2`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/article.py backend/app/routers/articles.py
git commit -m "feat: add progress endpoint and expose chapter nav in article detail"
```

---

## Task 11: Frontend types

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Add book/chapter types and extend ArticleDetail**

In `frontend/src/types/index.ts`, add:

```typescript
export interface BookListItem {
  id: string;
  title: string;
  cover_image_url: string | null;
  source_category: string | null;
  created_at: string;
  chapter_count: number;
  read_chapter_order: number | null;
}

export interface ChapterListItem {
  id: string;
  title: string;
  chapter_order: number;
  word_count: number;
  last_sentence_index: number | null;
}

export interface BookDetail {
  id: string;
  title: string;
  cover_image_url: string | null;
  source_category: string | null;
  created_at: string;
  chapters: ChapterListItem[];
  continue_article_id: string | null;
  continue_sentence_index: number | null;
}
```

And add these optional fields to the existing `ArticleDetail` interface:

```typescript
  book_id?: string | null;
  chapter_order?: number | null;
  prev_article_id?: string | null;
  next_article_id?: string | null;
  last_sentence_index?: number | null;
```

- [ ] **Step 2: Verify the frontend still typechecks/builds**

From `frontend/`:

```bash
npx tsc --noEmit
```

Expected: no errors (exit 0).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat: add book/chapter frontend types"
```

---

## Task 12: Book detail page + route

**Files:**
- Create: `frontend/src/pages/BookDetailPage.tsx`
- Modify: `frontend/src/App.tsx` (add route)

- [ ] **Step 1: Create the BookDetailPage**

Create `frontend/src/pages/BookDetailPage.tsx`:

```tsx
import { useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { api } from "../api/client";
import type { BookDetail } from "../types";

export default function BookDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");

  const { data: book, isLoading } = useQuery({
    queryKey: ["book", id],
    queryFn: () => api.get(`books/${id}`).json<BookDetail>(),
    enabled: !!id,
  });

  const addChapter = useMutation({
    mutationFn: (body: { title: string; raw_text: string }) =>
      api.post(`books/${id}/chapters`, { json: body }).json(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["book", id] });
      setTitle("");
      setText("");
      setAdding(false);
    },
  });

  if (isLoading || !book) {
    return <div className="flex items-center justify-center h-screen text-gray-400">加载中...</div>;
  }

  return (
    <div className="min-h-screen bg-white">
      <div className="max-w-3xl mx-auto px-6 py-8">
        <Link to="/" className="inline-flex items-center gap-1 text-gray-400 hover:text-gray-600 text-sm mb-4">
          <ArrowLeft size={16} /> 返回
        </Link>
        <h1 className="text-2xl font-bold text-gray-900 mb-1">{book.title}</h1>
        <p className="text-sm text-gray-400 mb-6">{book.chapters.length} 章</p>

        {book.continue_article_id && (
          <button
            onClick={() => navigate(`/articles/${book.continue_article_id}`)}
            className="bg-blue-500 text-white px-5 py-2.5 rounded-lg text-sm font-medium hover:bg-blue-600 transition-colors mb-6"
          >
            继续阅读
          </button>
        )}

        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold text-gray-800">章节目录</h2>
          <button
            onClick={() => setAdding(!adding)}
            className="text-sm text-blue-500 hover:text-blue-600 font-medium"
          >
            + 添加章节
          </button>
        </div>

        {adding && (
          <div className="bg-gray-50 rounded-xl border border-gray-200 p-5 mb-5">
            <input
              type="text" value={title} onChange={(e) => setTitle(e.target.value)}
              placeholder="章节标题"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 mb-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
            />
            <textarea
              value={text} onChange={(e) => setText(e.target.value)}
              placeholder="在此粘贴本章英文..." rows={10}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 mb-4 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-400 resize-none"
            />
            <div className="flex gap-2">
              <button
                onClick={() => addChapter.mutate({ title, raw_text: text })}
                disabled={!title.trim() || !text.trim() || addChapter.isPending}
                className="bg-blue-500 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-600 disabled:opacity-50"
              >
                {addChapter.isPending ? "处理中..." : "提交"}
              </button>
              <button onClick={() => setAdding(false)} className="bg-gray-200 text-gray-700 px-4 py-2 rounded-lg text-sm font-medium hover:bg-gray-300">
                取消
              </button>
            </div>
          </div>
        )}

        <div className="space-y-2">
          {book.chapters.map((ch) => (
            <Link
              key={ch.id} to={`/articles/${ch.id}`}
              className="flex items-center justify-between bg-white border border-gray-200 rounded-xl p-4 hover:shadow-sm transition-shadow"
            >
              <div className="min-w-0">
                <span className="text-xs text-gray-400 mr-2">第 {ch.chapter_order} 章</span>
                <span className="font-medium text-gray-800">{ch.title}</span>
              </div>
              <span className="text-xs text-gray-400 shrink-0 ml-3">
                {ch.last_sentence_index != null ? "已读" : ""} {ch.word_count.toLocaleString()} 词
              </span>
            </Link>
          ))}
          {book.chapters.length === 0 && (
            <p className="text-center text-gray-400 py-12 text-sm">还没有章节，点击「+ 添加章节」开始</p>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add the route**

In `frontend/src/App.tsx`, add the import:

```tsx
import BookDetailPage from "./pages/BookDetailPage";
```

And add the route (after the `/articles/:id` route):

```tsx
        <Route path="/books/:id" element={<ProtectedRoute><BookDetailPage /></ProtectedRoute>} />
```

- [ ] **Step 3: Verify in the browser**

Ensure both servers run. Open `http://localhost:5173`, then navigate to `http://localhost:5173/books/<BOOK_ID>` (use the book id from earlier). Confirm: book title, "继续阅读" button, chapter list with "第 1 章 / 第 2 章", and the "+ 添加章节" form adds a chapter that appears in the list. Also run `npx tsc --noEmit` from `frontend/` — expect no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/BookDetailPage.tsx frontend/src/App.tsx
git commit -m "feat: add book detail page with chapter list and add-chapter"
```

---

## Task 13: List page — merge books + articles, add create-book

**Files:**
- Modify: `frontend/src/pages/ArticleListPage.tsx`

- [ ] **Step 1: Fetch books alongside articles and add a create-book mutation**

In `frontend/src/pages/ArticleListPage.tsx`, add the import:

```tsx
import type { ArticleListItem, BookListItem } from "../types";
```

Add a books query next to the existing articles query:

```tsx
  const { data: books } = useQuery({
    queryKey: ["books"],
    queryFn: () => api.get("books").json<BookListItem[]>(),
  });
```

Add create-book state and mutation (near the other useState/useMutation hooks):

```tsx
  const [bookTitle, setBookTitle] = useState("");
  const [isCreatingBook, setIsCreatingBook] = useState(false);

  const createBookMutation = useMutation({
    mutationFn: (body: { title: string }) => api.post("books", { json: body }).json<BookListItem>(),
    onSuccess: (book) => {
      queryClient.invalidateQueries({ queryKey: ["books"] });
      setBookTitle("");
      setIsCreatingBook(false);
      navigate(`/books/${book.id}`);
    },
  });
```

Add `useNavigate` import and hook:

```tsx
import { Link, useNavigate } from "react-router-dom";
```

```tsx
  const navigate = useNavigate();
```

- [ ] **Step 2: Render a "create book" button + form and book cards above articles**

Add a "创建书" button next to the existing "+ 添加文章" button:

```tsx
          <button
            onClick={() => setIsCreatingBook(!isCreatingBook)}
            className="bg-gray-100 text-gray-700 px-4 py-2 rounded-lg text-sm font-medium hover:bg-gray-200 transition-colors mr-2"
          >
            + 创建书
          </button>
```

Add the create-book form (place it just above the existing article create form `{isCreating && ...}`):

```tsx
        {isCreatingBook && (
          <div className="bg-gray-50 rounded-xl border border-gray-200 p-6 mb-6">
            <h2 className="font-semibold text-gray-800 mb-4">创建一本书</h2>
            <input
              type="text" value={bookTitle} onChange={(e) => setBookTitle(e.target.value)}
              placeholder="书名"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 mb-4 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
            />
            <div className="flex gap-2">
              <button
                onClick={() => createBookMutation.mutate({ title: bookTitle })}
                disabled={!bookTitle.trim() || createBookMutation.isPending}
                className="bg-blue-500 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-600 disabled:opacity-50"
              >
                {createBookMutation.isPending ? "创建中..." : "创建"}
              </button>
              <button onClick={() => setIsCreatingBook(false)} className="bg-gray-200 text-gray-700 px-4 py-2 rounded-lg text-sm font-medium hover:bg-gray-300">
                取消
              </button>
            </div>
          </div>
        )}
```

Add book cards above the article list (just before `<div className="space-y-3">` that renders articles):

```tsx
        {books && books.length > 0 && (
          <div className="space-y-3 mb-3">
            {books.map((book) => (
              <Link
                key={book.id} to={`/books/${book.id}`}
                className="flex items-center justify-between bg-white border border-gray-200 rounded-xl p-4 hover:shadow-sm transition-shadow"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="shrink-0 text-xs bg-amber-50 text-amber-600 border border-amber-100 px-1.5 py-0.5 rounded font-medium">书</span>
                    <h3 className="font-medium text-gray-800 truncate">{book.title}</h3>
                  </div>
                  <p className="text-xs text-gray-400 mt-0.5">
                    {book.chapter_count} 章
                    {book.read_chapter_order != null && ` · 读到第 ${book.read_chapter_order} 章`}
                  </p>
                </div>
                <span className="text-gray-300 text-sm">📖</span>
              </Link>
            ))}
          </div>
        )}
```

- [ ] **Step 3: Verify in the browser**

With both servers running, open `http://localhost:5173`. Confirm: a "+ 创建书" button exists; clicking it shows a name-only form; creating a book navigates to its detail page; returning to the list shows the book as a card with a "书" badge and "N 章" above the standalone articles. Run `npx tsc --noEmit` from `frontend/` — expect no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ArticleListPage.tsx
git commit -m "feat: show books on list page and add create-book flow"
```

---

## Task 14: Reader — prev/next chapter nav + record/restore progress

**Files:**
- Modify: `frontend/src/pages/ArticleReaderPage.tsx`

- [ ] **Step 1: Restore scroll to last_sentence_index on load**

In `frontend/src/pages/ArticleReaderPage.tsx`, after the `article` query resolves, add an effect that scrolls to the saved sentence. The reader renders tokens; each token carries `sentence_index`. Add a `data-sentence-index` attribute hook by scrolling to the first token element of the target sentence.

Add this effect after the existing `initFromArticle` effect:

```tsx
  useEffect(() => {
    if (article && article.last_sentence_index && article.last_sentence_index > 0) {
      // wait for tokens to render, then scroll to the sentence anchor
      const t = setTimeout(() => {
        const el = document.querySelector(`[data-sentence-index="${article.last_sentence_index}"]`);
        el?.scrollIntoView({ behavior: "auto", block: "center" });
      }, 100);
      return () => clearTimeout(t);
    }
  }, [article]);
```

- [ ] **Step 2: Add a sentence anchor in the rendered body**

For the scroll target to exist, the rendered tokens need a `data-sentence-index` marker. In `frontend/src/components/ArticleBody.tsx`, wrap the first token of each sentence with the attribute. Replace the token map with one that tags sentence starts:

```tsx
      {tokens.map((token, i) => {
        const isSentenceStart = i === 0 || tokens[i - 1].sentence_index !== token.sentence_index;
        return (
          <span key={token.index} data-sentence-index={isSentenceStart ? token.sentence_index : undefined}>
            <WordToken
              token={token}
              articleId={articleId}
              sentences={sentences}
              autoOpenSidebar={autoOpenSidebar}
            />
          </span>
        );
      })}
```

- [ ] **Step 3: Record progress on scroll (debounced)**

In `ArticleReaderPage.tsx`, add a scroll handler on the scrollable container that finds the topmost visible sentence and PUTs progress. Add near the top of the component:

```tsx
  const progressMutation = useMutation({
    mutationFn: (body: { last_sentence_index: number }) =>
      api.put(`articles/${id}/progress`, { json: body }),
  });
```

(Add `useMutation` to the `@tanstack/react-query` import and `useRef` to the React import.)

Add a debounced scroll handler attached to the scroll container (`<div className="flex-1 overflow-y-auto">`):

```tsx
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const container = e.currentTarget;
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      const anchors = container.querySelectorAll("[data-sentence-index]");
      const top = container.getBoundingClientRect().top;
      let current = 0;
      for (const a of Array.from(anchors)) {
        if (a.getBoundingClientRect().top <= top + 80) {
          current = Number((a as HTMLElement).dataset.sentenceIndex);
        } else break;
      }
      if (id) progressMutation.mutate({ last_sentence_index: current });
    }, 600);
  };
```

Attach it: `<div className="flex-1 overflow-y-auto" onScroll={handleScroll}>`.

- [ ] **Step 4: Add prev/next chapter navigation**

In `ArticleReaderPage.tsx`, below the `<ArticleBody />` block (inside the content container), add chapter nav shown only when the article belongs to a book:

```tsx
          {article.book_id && (
            <div className="flex items-center justify-between mt-12 pt-6 border-t border-gray-100">
              {article.prev_article_id ? (
                <Link to={`/articles/${article.prev_article_id}`} className="text-sm text-blue-500 hover:text-blue-600">← 上一章</Link>
              ) : <span />}
              <Link to={`/books/${article.book_id}`} className="text-xs text-gray-400 hover:text-gray-600">目录</Link>
              {article.next_article_id ? (
                <Link to={`/articles/${article.next_article_id}`} className="text-sm text-blue-500 hover:text-blue-600">下一章 →</Link>
              ) : <span />}
            </div>
          )}
```

- [ ] **Step 5: Verify in the browser**

With both servers running and a book that has 2+ chapters: open chapter one via `http://localhost:5173/books/<BOOK_ID>` → click a chapter. Confirm: "上一章 / 目录 / 下一章" footer appears (上一章 hidden on chapter 1); clicking 下一章 loads chapter 2. Scroll down a long chapter, leave, reopen from "继续阅读" — it should scroll back near where you left off. Run `npx tsc --noEmit` from `frontend/` — expect no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/ArticleReaderPage.tsx frontend/src/components/ArticleBody.tsx
git commit -m "feat: add chapter navigation and reading-progress save/restore in reader"
```

---

## Self-Review Notes

- **Spec coverage:** books table (T1), articles columns (T2), reading_history columns (T3), schemas (T4), create/list books (T5), add chapter reusing pipeline (T6), book detail + resume (T7), delete cascade (T8), edit + drift reset (T9), progress + chapter nav fields (T10), all five frontend pieces (T11-T14: types, book detail page, list merge + create-book, reader nav + progress). Edit-permission (own articles only) is enforced by the `Article.user_id == current_user.id` filter in T9. Public-library admin management is explicitly Post-MVP and not in this plan.
- **create_all caveat:** New `books` table is auto-created; added columns on existing tables require the explicit `ALTER TABLE` steps (T2, T3) — called out because this project has no Alembic.
- **Type consistency:** `last_sentence_index`, `chapter_order`, `continue_article_id`, `prev_article_id`/`next_article_id`, `chapter_count`, `read_chapter_order` are named identically across backend schemas (T4, T10) and frontend types (T11) and their consumers (T12-T14).
