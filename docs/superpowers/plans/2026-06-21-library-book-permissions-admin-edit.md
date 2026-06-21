# 公共库图书权限 + 管理员编辑图书 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hide the "+ 添加章节" button on saved public-library books for non-owners, and give admins a way to edit a library book's own metadata (title / cover / category).

**Architecture:** Bug 1 — expose `is_owner` from the book-detail API so the shared `/books/:id` page can hide the add-chapter affordance for saved library books. Bug 2 — add a `PATCH /admin/library/books/{id}` endpoint plus a dual-mode (create/edit) book form in the admin Books tab, mirroring the existing pattern in the Articles tab.

**Tech Stack:** FastAPI + Pydantic + SQLAlchemy (async) backend; React + TanStack Query + TypeScript frontend.

## Global Constraints

- Backend is async (`async/await`) throughout — keep it consistent.
- Server-side state via TanStack Query; client UI state via Zustand. New mutations must invalidate the relevant query keys.
- Admin endpoints are guarded by `require_content_admin` (from `app.dependencies`).
- Library book lookups must filter `Book.is_library == True`.
- Backend tests are pure-Python (schema/logic level) — no DB or HTTP harness exists. Run with `.venv/bin/pytest`.
- Frontend has no unit-test runner; verification is `npm run build` (runs `tsc`) plus manual checks.
- Chinese UI copy must match existing tone (e.g. "编辑图书", "保存修改").

---

### Task 1: Add `is_owner` to book-detail schema + endpoint (Bug 1 backend)

**Files:**
- Modify: `backend/app/schemas/book.py` (`BookDetailResponse`, ~line 42-50)
- Modify: `backend/app/routers/books.py` (`get_book`, ~line 202-211)
- Test: `backend/tests/test_library_books.py`

**Interfaces:**
- Produces: `BookDetailResponse.is_owner: bool` (default `False`), returned by `GET /books/{book_id}`. Frontend Task 3 consumes it.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_library_books.py`:

```python
def test_book_detail_response_has_is_owner_default():
    from app.schemas.book import BookDetailResponse
    from datetime import datetime, timezone

    resp = BookDetailResponse(
        id="abc",
        title="Test",
        cover_image_url=None,
        source_category=None,
        created_at=datetime.now(timezone.utc),
        chapters=[],
    )
    assert resp.is_owner is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_library_books.py::test_book_detail_response_has_is_owner_default -v`
Expected: FAIL with `TypeError`/`ValidationError` or `AttributeError` — `is_owner` not a field.

- [ ] **Step 3: Add the field to the schema**

In `backend/app/schemas/book.py`, `BookDetailResponse`, add after `continue_sentence_index`:

```python
class BookDetailResponse(BaseModel):
    id: str
    title: str
    cover_image_url: str | None
    source_category: str | None
    created_at: datetime
    chapters: list[ChapterListItem]
    continue_article_id: str | None = None
    continue_sentence_index: int | None = None
    is_owner: bool = False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_library_books.py::test_book_detail_response_has_is_owner_default -v`
Expected: PASS

- [ ] **Step 5: Set `is_owner` in the endpoint**

In `backend/app/routers/books.py`, `get_book`, update the `return BookDetailResponse(...)` to include:

```python
    return BookDetailResponse(
        id=book.id,
        title=book.title,
        cover_image_url=book.cover_image_url,
        source_category=book.source_category,
        created_at=book.created_at,
        chapters=chapter_items,
        continue_article_id=continue_article_id,
        continue_sentence_index=continue_sentence_index,
        is_owner=(book.user_id == current_user.id),
    )
```

- [ ] **Step 6: Run full backend test suite**

Run: `.venv/bin/pytest -q`
Expected: PASS (all existing tests + new one)

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/book.py backend/app/routers/books.py backend/tests/test_library_books.py
git commit -m "feat: expose is_owner on book detail so non-owners hide add-chapter"
```

---

### Task 2: Add `BookPatchRequest` schema + `PATCH /admin/library/books/{id}` (Bug 2 backend)

**Files:**
- Modify: `backend/app/schemas/book.py` (add `BookPatchRequest` near `ChapterPatchRequest`, ~line 65)
- Modify: `backend/app/routers/admin.py` (import + new route after `create_library_book`, ~line 145)
- Test: `backend/tests/test_admin_schemas.py`

**Interfaces:**
- Produces: `BookPatchRequest(title: str | None, cover_image_url: str | None, source_category: str | None)` — all default `None`.
- Produces: `PATCH /admin/library/books/{book_id}` → `LibraryBookListItem`, guarded by `require_content_admin`. Frontend Task 4 consumes it.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_admin_schemas.py`:

```python
def test_book_patch_all_none():
    from app.schemas.book import BookPatchRequest
    req = BookPatchRequest()
    assert req.title is None
    assert req.cover_image_url is None
    assert req.source_category is None


def test_book_patch_partial():
    from app.schemas.book import BookPatchRequest
    req = BookPatchRequest(title="New Title")
    assert req.title == "New Title"
    assert req.cover_image_url is None
    assert req.source_category is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_admin_schemas.py::test_book_patch_all_none tests/test_admin_schemas.py::test_book_patch_partial -v`
Expected: FAIL — `ImportError: cannot import name 'BookPatchRequest'`.

- [ ] **Step 3: Add the schema**

In `backend/app/schemas/book.py`, add after `ChapterPatchRequest`:

```python
class BookPatchRequest(BaseModel):
    title: str | None = None
    cover_image_url: str | None = None
    source_category: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_admin_schemas.py::test_book_patch_all_none tests/test_admin_schemas.py::test_book_patch_partial -v`
Expected: PASS

- [ ] **Step 5: Add the endpoint**

In `backend/app/routers/admin.py`, update the book-schema import line:

```python
from app.schemas.book import BookCreateRequest, BookPatchRequest, ChapterCreateRequest, ChapterPatchRequest, LibraryBookListItem
```

Then add this route immediately after `create_library_book` (before `delete_library_book`):

```python
@router.patch("/library/books/{book_id}", response_model=LibraryBookListItem)
async def update_library_book(
    book_id: str,
    body: BookPatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_content_admin),
):
    book = await db.scalar(
        select(Book).where(Book.id == book_id, Book.is_library == True)  # noqa: E712
    )
    if not book:
        raise HTTPException(status_code=404, detail="Library book not found")

    if body.title is not None:
        book.title = body.title
    if body.cover_image_url is not None:
        book.cover_image_url = body.cover_image_url
    if body.source_category is not None:
        book.source_category = body.source_category

    await db.commit()

    chapter_count = await db.scalar(
        select(func.count(Article.id)).where(Article.book_id == book_id)
    )
    item = LibraryBookListItem.model_validate(book)
    item.chapter_count = chapter_count or 0
    return item
```

Note: `select`, `func`, `Book`, `Article`, `HTTPException`, `require_content_admin` are already imported in `admin.py`.

- [ ] **Step 6: Run full backend test suite**

Run: `.venv/bin/pytest -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/book.py backend/app/routers/admin.py backend/tests/test_admin_schemas.py
git commit -m "feat: PATCH /admin/library/books/{id} to edit book metadata"
```

---

### Task 3: Hide "+ 添加章节" for non-owners (Bug 1 frontend)

**Files:**
- Modify: `frontend/src/types/index.ts` (`BookDetail`, ~line 81-90)
- Modify: `frontend/src/pages/BookDetailPage.tsx` (~line 55-90)

**Interfaces:**
- Consumes: `BookDetailResponse.is_owner` from Task 1.

- [ ] **Step 1: Add `is_owner` to the `BookDetail` type**

In `frontend/src/types/index.ts`, `BookDetail`:

```typescript
export interface BookDetail {
  id: string;
  title: string;
  cover_image_url: string | null;
  source_category: string | null;
  created_at: string;
  chapters: ChapterListItem[];
  continue_article_id: string | null;
  continue_sentence_index: number | null;
  is_owner: boolean;
}
```

- [ ] **Step 2: Gate the add-chapter button on `book.is_owner`**

In `frontend/src/pages/BookDetailPage.tsx`, the "章节目录" header block currently renders the button unconditionally. Wrap the button so it only shows for owners:

```tsx
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold text-gray-800">章节目录</h2>
          {book.is_owner && (
            <button
              onClick={() => setAdding(!adding)}
              className="text-sm text-blue-500 hover:text-blue-600 font-medium"
            >
              + 添加章节
            </button>
          )}
        </div>
```

- [ ] **Step 3: Gate the add-chapter form on `book.is_owner`**

In the same file, the `{adding && ( ... )}` form block should never appear for non-owners. Since `adding` can only become true via the now-hidden button, this is already safe — but to be defensive, change the guard to:

```tsx
        {book.is_owner && adding && (
```

(Leave the rest of the form block unchanged.)

- [ ] **Step 4: Verify the build compiles**

Run: `cd frontend && npm run build`
Expected: `tsc` passes with no type errors; vite build succeeds.

- [ ] **Step 5: Manual check**

Start backend + frontend. As a normal user, save a public-library book, open `/books/:id` → no "+ 添加章节" button. Open one of your own books → button present and add still works.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/pages/BookDetailPage.tsx
git commit -m "fix: hide add-chapter on saved library books for non-owners"
```

---

### Task 4: Dual-mode book form + edit button in admin Books tab (Bug 2 frontend)

**Files:**
- Modify: `frontend/src/pages/AdminPage.tsx` (`BooksTab` and its `BookFormState`, ~line 357-664)

**Interfaces:**
- Consumes: `PATCH /admin/library/books/{id}` from Task 2.

- [ ] **Step 1: Extend `BookFormState` to support edit mode**

In `frontend/src/pages/AdminPage.tsx`, replace the `BookFormState` type and `EMPTY_BOOK_FORM` (~line 357-363):

```tsx
type BookFormState = {
  mode: "create" | "edit";
  editId: string | null;
  title: string;
  cover_image_url: string;
  source_category: string;
};

const EMPTY_BOOK_FORM: BookFormState = {
  mode: "create",
  editId: null,
  title: "",
  cover_image_url: "",
  source_category: "",
};
```

- [ ] **Step 2: Add the edit mutation**

In `BooksTab`, add after `createBookMutation` (~line 400):

```tsx
  const editBookMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: object }) =>
      api.patch(`admin/library/books/${id}`, { json: body }).json(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["library-books"] });
      setBookForm(EMPTY_BOOK_FORM);
      setBookFormError("");
    },
    onError: async (err: any) => {
      const msg = await err.response?.json().catch(() => null);
      setBookFormError(msg?.detail ?? "保存失败");
    },
  });
```

- [ ] **Step 3: Branch the submit handler on mode**

Replace `handleBookSubmit` (~line 466-474):

```tsx
  function handleBookSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBookFormError("");
    const payload = {
      title: bookForm.title,
      cover_image_url: bookForm.cover_image_url || null,
      source_category: bookForm.source_category || null,
    };
    if (bookForm.mode === "create") {
      createBookMutation.mutate(payload);
    } else if (bookForm.editId) {
      editBookMutation.mutate({ id: bookForm.editId, body: payload });
    }
  }
```

- [ ] **Step 4: Add an edit button to each book row**

In the book list, next to the delete button (~line 510-516), add a Pencil edit button before it. `Pencil` is already imported. Use `e.stopPropagation()` so the row's expand/collapse `onClick` doesn't fire:

```tsx
              <div className="flex items-center gap-1 shrink-0">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setBookForm({
                      mode: "edit",
                      editId: book.id,
                      title: book.title,
                      cover_image_url: book.cover_image_url ?? "",
                      source_category: book.source_category ?? "",
                    });
                    setBookFormError("");
                  }}
                  className="p-1.5 text-gray-400 hover:text-blue-500 transition-colors"
                  title="编辑图书"
                >
                  <Pencil size={14} />
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); handleDeleteBook(book); }}
                  className="p-1.5 text-gray-400 hover:text-red-500 transition-colors"
                  title="删除图书"
                >
                  <Trash2 size={14} />
                </button>
              </div>
```

This replaces the existing single delete `<button>` (which is currently a direct child of the row flex container).

- [ ] **Step 5: Make the book form header + button mode-aware**

Replace the "新建图书" form header and submit button. The header block (~line 536-537):

```tsx
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-gray-700">
              {bookForm.mode === "create" ? "新建图书" : "编辑图书"}
            </h2>
            {bookForm.mode === "edit" && (
              <button onClick={() => setBookForm(EMPTY_BOOK_FORM)} className="text-gray-400 hover:text-gray-600">
                <X size={16} />
              </button>
            )}
          </div>
          <form onSubmit={handleBookSubmit} className="space-y-3">
```

(`X` is already imported.) The submit button (~line 564-570):

```tsx
            <button
              type="submit"
              disabled={createBookMutation.isPending || editBookMutation.isPending}
              className="w-full py-2 bg-blue-500 text-white text-sm font-medium rounded-lg hover:bg-blue-600 disabled:opacity-50 transition-colors"
            >
              {bookForm.mode === "create"
                ? createBookMutation.isPending ? "创建中..." : "创建图书"
                : editBookMutation.isPending ? "保存中..." : "保存修改"}
            </button>
```

- [ ] **Step 6: Verify the build compiles**

Run: `cd frontend && npm run build`
Expected: `tsc` passes; vite build succeeds.

- [ ] **Step 7: Manual check**

As admin → 内容管理 → 图书 tab. Click the Pencil on a book → form switches to "编辑图书" with fields populated → change title/cover/category → "保存修改" → list refreshes with the new values. Click X → form returns to "新建图书" empty. Confirm clicking Pencil does NOT toggle the chapter expand/collapse.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/AdminPage.tsx
git commit -m "feat: admin can edit library book title/cover/category"
```

---

## Self-Review

**Spec coverage:**
- Bug 1 backend (`is_owner` field + endpoint) → Task 1 ✓
- Bug 1 frontend (hide button + form) → Task 3 ✓
- Bug 2 backend (`BookPatchRequest` + PATCH endpoint) → Task 2 ✓
- Bug 2 frontend (dual-mode form + edit button) → Task 4 ✓
- Out-of-scope items (read-only badge, personal-book editing, chapter/translation logic) → correctly untouched ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases" — all steps show concrete code and exact commands.

**Type consistency:** `is_owner: bool` (backend, default False) ↔ `is_owner: boolean` (frontend, required, always set by endpoint). `BookPatchRequest` fields match the frontend payload keys (`title`, `cover_image_url`, `source_category`). `BookFormState` shape consistent across Steps 1–5 of Task 4. Endpoint path `admin/library/books/{id}` consistent between Task 2 (define) and Task 4 (consume).
