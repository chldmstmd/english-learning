# Admin UI for Library Content Management — Design Spec

## Goal

Build a `/admin` page that lets content admins create, edit, and delete public library articles and books (including chapters) through a frontend UI.

## Architecture

Single-page admin area at `/admin` with two tabs (文章 / 图书). Left panel lists existing content; right panel hosts inline create/edit forms. No nested routes. Role-gated: only `content_admin` and `super_admin` may access.

**Tech Stack:** FastAPI (backend), React + TanStack Query + Tailwind CSS (frontend)

---

## Backend Changes

All new routes live under `/admin` prefix, protected by `require_content_admin` dependency.

### Library Article Routes

**`POST /admin/library/articles`**
- Body: `title: str`, `raw_text: str`, `difficulty: "level1" | "level2" | None`, `source_category: str | None`
- Creates `Article` with `is_library=True`, `user_id=<admin's id>`
- Runs `nlp_service.tokenize(raw_text)` to populate `tokens`, `sentences`, `word_count`
- Enforces 10,000-word limit (400 if exceeded)
- Fires `asyncio.create_task(batch_translation_service.translate_article(article.id))` after commit
- Returns `LibraryArticleListItem`

**`PATCH /admin/library/articles/{article_id}`**
- Body (all optional): `title: str`, `difficulty: str | None`, `source_category: str | None`
- Only updates metadata fields — raw_text/tokens/sentences are immutable via this endpoint
- 404 if article not found or `is_library=False`
- Returns updated `LibraryArticleListItem`

**`DELETE /admin/library/articles/{article_id}`**
- 404 if article not found or `is_library=False`
- Explicitly deletes related annotations, reading history rows, and bookmarks, then deletes the article (consistent with existing `delete_book` pattern)
- Returns 204

### Library Book Routes

**`POST /admin/library/books`**
- Body: `title: str`, `cover_image_url: str | None`, `source_category: str | None`
- Creates `Book` with `is_library=True`, `user_id=<admin's id>`
- Returns `LibraryBookListItem`

**`DELETE /admin/library/books/{book_id}`**
- 404 if book not found or `is_library=False`
- Deletes all chapters (Articles with `book_id`), then the Book
- Returns 204

### Library Book Chapter Routes

**`POST /admin/library/books/{book_id}/chapters`**
- Body: `title: str`, `raw_text: str`
- Validates book exists and `is_library=True`; no owner check
- Runs `nlp_service.tokenize`, enforces 10,000-word limit
- Assigns next `chapter_order` (max + 1)
- Fires `batch_translation_service.translate_article` after commit
- Returns `ArticleListItem`

**`DELETE /admin/library/books/{book_id}/chapters/{chapter_id}`**
- 404 if chapter not found or doesn't belong to book
- Deletes the Article; does not reorder remaining chapters
- Returns 204

### Schemas

New `AdminArticleCreateRequest`:
```python
class AdminArticleCreateRequest(BaseModel):
    title: str
    raw_text: str
    difficulty: str | None = None
    source_category: str | None = None
```

New `AdminArticlePatchRequest`:
```python
class AdminArticlePatchRequest(BaseModel):
    title: str | None = None
    difficulty: str | None = None
    source_category: str | None = None
```

Reuse existing `BookCreateRequest`, `ChapterCreateRequest`, `LibraryBookListItem`, `LibraryArticleListItem`.

---

## Frontend Changes

### Auth: add `role` to `AuthUser`

`types/index.ts`:
```ts
export interface AuthUser {
  id: string;
  email: string;
  role: string;
}
```

`/auth/me` already returns `role`; it just needs to be stored and typed. Login flow already persists the full user object to localStorage.

### Route guard: `AdminRoute`

New component `components/AdminRoute.tsx`:
- Reads `user.role` from auth store
- Renders children if role is `content_admin` or `super_admin`
- Redirects to `/` otherwise

### Routing (`App.tsx`)

Add:
```tsx
<Route path="/admin" element={<AdminRoute><AdminPage /></AdminRoute>} />
```

### Navigation (`PageNav.tsx`)

Show a「管理」link to `/admin` when `user.role` is `content_admin` or `super_admin`.

### `AdminPage.tsx`

**Tab state:** `"articles" | "books"`, default `"articles"`

**Articles tab layout:**
- Left panel (scrollable list): fetches `GET /library?page_size=100`. Each row shows title, difficulty badge, category, date. Two icon buttons: pencil (edit) and trash (delete with confirm).
- Right panel: form with fields title (text input), raw_text (textarea, tall), difficulty (select: 全部/Level1/Level2), source_category (select matching existing CATEGORIES). Submit calls `POST /admin/library/articles`. When editing (pencil clicked), form pre-fills title/difficulty/category and submit calls `PATCH /admin/library/articles/{id}`; raw_text field is hidden in edit mode. Cancel button resets to create mode.

**Books tab layout:**
- Left panel: fetches `GET /library/books`. Each book row shows title, chapter count, trash button (delete book with confirm). Clicking a book row expands it inline to show its chapter list (title, word count, trash button per chapter).
- Right panel: two stacked sections:
  1. 「新建图书」— title, cover_image_url (optional), source_category select. Submit calls `POST /admin/library/books`.
  2. 「添加章节」— book selector (dropdown of existing library books), chapter title, raw_text textarea. Submit calls `POST /admin/library/books/{book_id}/chapters`.

**Query invalidation:**
- After article create/edit/delete: invalidate `["library"]`
- After book create/delete: invalidate `["library-books"]`
- After chapter add/delete: invalidate `["library-books"]`

**Error handling:** Show inline error message below form on API failure (non-blocking toast not needed; simple red text is fine).

---

## What Is NOT in Scope

- Editing article body text (delete + recreate instead)
- Reordering chapters (chapter_order is append-only)
- Image upload (cover_image_url is a plain text URL input)
- VOA sync trigger (already exists at `POST /admin/sync-voa`, not surfaced in this UI)
- User management

---

## Testing

Backend unit tests (schema-level, no DB):
- `AdminArticleCreateRequest` rejects missing `title` or `raw_text`
- `AdminArticlePatchRequest` allows all-None body (no-op patch)
- `LibraryArticleListItem` and `LibraryBookListItem` defaults remain correct

No integration tests (consistent with existing test style in this repo).
