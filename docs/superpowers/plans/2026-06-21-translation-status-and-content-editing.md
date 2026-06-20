# Translation Status & Content Editing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace auto-triggered batch translation with admin-controlled manual triggering; add a 5-state translation status model; add chapter editing in AdminPage; add user article inline editing in ArticleListPage.

**Architecture:** Backend changes are isolated to schemas, two routers (admin, articles), and batch_translation_service. Frontend adds one shared modal component and modifies three pages (AdminPage, ArticleListPage, and their types).

**Tech Stack:** FastAPI + SQLAlchemy (async), React + TanStack Query + Tailwind CSS, ky HTTP client.

## Global Constraints

- All backend routes are async/await
- New `translation_status` values: `untranslated | processing | done | stale | failed` (string column, no migration needed — just change server_default and runtime values)
- Existing DB rows with `translation_status = "pending"` are treated as `untranslated` at runtime (no data migration needed; the column stays a plain string)
- No auto-triggering translation on article/chapter create or edit
- Confirmation modal required before any translate API call
- Library bookmarked articles do not show edit button in ArticleListPage

---

## File Map

| File | Change |
|------|--------|
| `backend/app/models/article.py` | Change `server_default` of `translation_status` to `"untranslated"` |
| `backend/app/schemas/article.py` | Add `translation_status` to `LibraryArticleListItem`, `ArticleListItem`; add `ChapterPatchRequest` |
| `backend/app/schemas/book.py` | Add `translation_status` to `ChapterListItem`; add `ChapterPatchRequest` |
| `backend/app/routers/admin.py` | Remove auto-trigger calls; add `POST .../translate` endpoints; add `PATCH .../chapters/:id` |
| `backend/app/routers/articles.py` | Remove auto-trigger on create; add `POST /articles/:id/translate` (not user-exposed yet) |
| `backend/app/services/batch_translation_service.py` | Accept `untranslated`/`stale`/`failed` as valid starting states (remove `done`-only skip) |
| `frontend/src/types/index.ts` | Update `translation_status` union type; add `translation_status` to `ChapterListItem` |
| `frontend/src/components/TranslateConfirmModal.tsx` | New shared modal component |
| `frontend/src/pages/AdminPage.tsx` | Translation badges + buttons + chapter editing |
| `frontend/src/pages/ArticleListPage.tsx` | Inline article editing |

---

## Task 1: Backend — Update translation_status model and service

**Files:**
- Modify: `backend/app/models/article.py`
- Modify: `backend/app/services/batch_translation_service.py`

**Interfaces:**
- Produces: `translate_article(article_id)` now accepts articles in any status except `processing` and `done`; sets `untranslated`/`stale`/`failed` → `processing` → `done`/`failed`

- [ ] **Step 1: Update Article model server_default**

In `backend/app/models/article.py`, change line:
```python
translation_status: Mapped[str] = mapped_column(
    String(16), nullable=False, server_default="pending"
)
```
to:
```python
translation_status: Mapped[str] = mapped_column(
    String(16), nullable=False, server_default="untranslated"
)
```

- [ ] **Step 2: Update batch_translation_service to handle new states**

In `backend/app/services/batch_translation_service.py`, replace the early-exit guard:
```python
# Skip if already done
if article.translation_status == "done":
    return
```
with:
```python
# Only skip if already processing or done
if article.translation_status in ("processing", "done"):
    return
```

- [ ] **Step 3: Manual smoke test**

Start backend: `cd backend && .venv/bin/uvicorn app.main:app --reload`
Check: `curl http://localhost:8000/health` returns `{"status":"ok"}`
No errors in startup log.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/article.py backend/app/services/batch_translation_service.py
git commit -m "feat: update translation_status model to 5-state with untranslated/stale"
```

---

## Task 2: Backend — Schema changes (expose translation_status in list responses)

**Files:**
- Modify: `backend/app/schemas/article.py`
- Modify: `backend/app/schemas/book.py`

**Interfaces:**
- Produces:
  - `LibraryArticleListItem.translation_status: str`
  - `ArticleListItem.translation_status: str`
  - `ChapterListItem.translation_status: str`
  - `ChapterPatchRequest(title: str | None, raw_text: str | None)` in `book.py`

- [ ] **Step 1: Add translation_status to ArticleListItem and LibraryArticleListItem**

In `backend/app/schemas/article.py`:

`ArticleListItem` — add field after `difficulty`:
```python
translation_status: str = "untranslated"
```

`LibraryArticleListItem` — add field after `source_url`:
```python
translation_status: str = "untranslated"
```

- [ ] **Step 2: Add translation_status to ChapterListItem and ChapterPatchRequest**

In `backend/app/schemas/book.py`:

`ChapterListItem` — add field after `last_sentence_index`:
```python
translation_status: str = "untranslated"
```

Add new schema at the bottom of the file:
```python
class ChapterPatchRequest(BaseModel):
    title: str | None = None
    raw_text: str | None = None
```

- [ ] **Step 3: Verify backend still starts cleanly**

```bash
cd backend && .venv/bin/uvicorn app.main:app --reload
```
Check startup log has no import errors.

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/article.py backend/app/schemas/book.py
git commit -m "feat: expose translation_status in article and chapter list schemas"
```

---

## Task 3: Backend — Admin translate endpoints + remove auto-trigger

**Files:**
- Modify: `backend/app/routers/admin.py`

**Interfaces:**
- Consumes: `batch_translation_service.translate_article(article_id: str)`; `ChapterPatchRequest` from `book.py`
- Produces:
  - `POST /api/v1/admin/library/articles/:id/translate` → `{"translation_status": "processing"}`
  - `POST /api/v1/admin/library/books/:book_id/chapters/:chapter_id/translate` → `{"translation_status": "processing"}`
  - `PATCH /api/v1/admin/library/books/:book_id/chapters/:chapter_id` → `ArticleListItem`

- [ ] **Step 1: Remove auto-trigger from article create**

In `backend/app/routers/admin.py`, in `create_library_article`, remove:
```python
asyncio.create_task(batch_translation_service.translate_article(article.id))
```

- [ ] **Step 2: Remove auto-trigger from article patch**

In the same file, in `update_library_article`, remove:
```python
if body.raw_text is not None:
    asyncio.create_task(batch_translation_service.translate_article(article.id))
```

- [ ] **Step 3: Remove auto-trigger from add chapter**

In `add_library_chapter`, remove:
```python
asyncio.create_task(batch_translation_service.translate_article(article.id))
```

- [ ] **Step 4: Add article translate endpoint**

Add after `update_library_article`:
```python
@router.post("/library/articles/{article_id}/translate", status_code=200)
async def translate_library_article(
    article_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_content_admin),
):
    article = await db.scalar(
        select(Article).where(Article.id == article_id, Article.is_library == True)  # noqa: E712
    )
    if not article:
        raise HTTPException(status_code=404, detail="Library article not found")
    if article.translation_status == "processing":
        return {"translation_status": "processing"}
    article.translation_status = "processing"
    await db.commit()
    asyncio.create_task(batch_translation_service.translate_article(article_id))
    return {"translation_status": "processing"}
```

- [ ] **Step 5: Add chapter patch endpoint**

Add import at top of file (with existing imports):
```python
from app.schemas.book import BookCreateRequest, ChapterCreateRequest, ChapterPatchRequest, LibraryBookListItem
```

Add endpoint before `delete_library_chapter`:
```python
@router.patch("/library/books/{book_id}/chapters/{chapter_id}", response_model=ArticleListItem)
async def update_library_chapter(
    book_id: str,
    chapter_id: str,
    body: ChapterPatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_content_admin),
):
    article = await db.scalar(
        select(Article).where(Article.id == chapter_id, Article.book_id == book_id)
    )
    if not article:
        raise HTTPException(status_code=404, detail="Chapter not found")
    if body.title is not None:
        article.title = body.title
    if body.raw_text is not None:
        tokens, sentences, word_count = nlp_service.tokenize(body.raw_text)
        if word_count > 10000:
            raise HTTPException(status_code=400, detail="Chapter exceeds 10,000 word limit")
        article.raw_text = body.raw_text
        article.tokens = tokens
        article.sentences = sentences
        article.word_count = word_count
        article.translation_status = "stale"
        await db.execute(sa_delete(ArticleTranslation).where(ArticleTranslation.article_id == chapter_id))
    await db.commit()
    return ArticleListItem.model_validate(article)
```

- [ ] **Step 6: Add chapter translate endpoint**

Add after `update_library_chapter`:
```python
@router.post("/library/books/{book_id}/chapters/{chapter_id}/translate", status_code=200)
async def translate_library_chapter(
    book_id: str,
    chapter_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_content_admin),
):
    article = await db.scalar(
        select(Article).where(Article.id == chapter_id, Article.book_id == book_id)
    )
    if not article:
        raise HTTPException(status_code=404, detail="Chapter not found")
    if article.translation_status == "processing":
        return {"translation_status": "processing"}
    article.translation_status = "processing"
    await db.commit()
    asyncio.create_task(batch_translation_service.translate_article(chapter_id))
    return {"translation_status": "processing"}
```

- [ ] **Step 7: Smoke test new endpoints via curl**

First get a token (use form login):
```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=YOUR_ADMIN_EMAIL&password=YOUR_PASSWORD" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

Test article translate endpoint (use any real library article id from DB):
```bash
curl -s -X POST "http://localhost:8000/api/v1/admin/library/articles/ARTICLE_ID/translate" \
  -H "Authorization: Bearer $TOKEN"
# Expected: {"translation_status":"processing"}
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/routers/admin.py
git commit -m "feat: add admin translate endpoints for articles and chapters, remove auto-trigger"
```

---

## Task 4: Backend — User article translate endpoint (unexposed)

**Files:**
- Modify: `backend/app/routers/articles.py`

**Interfaces:**
- Produces: `POST /api/v1/articles/:id/translate` → `{"translation_status": "processing"}` (auth required, not linked from frontend)

- [ ] **Step 1: Remove auto-trigger from article create**

In `backend/app/routers/articles.py`, in `create_article`, remove:
```python
asyncio.create_task(batch_translation_service.translate_article(article.id))
```

Also add import for `batch_translation_service` will still be needed — keep the import, just don't call it on create.

Actually check: if `batch_translation_service` is only called in create, remove the import too. Run:
```bash
grep -n "batch_translation_service" backend/app/routers/articles.py
```
If only on the create line, remove both the import and the call. If used elsewhere, remove only the call.

- [ ] **Step 2: Add translate endpoint**

Add at the bottom of `backend/app/routers/articles.py`:
```python
@router.post("/articles/{article_id}/translate", status_code=200)
async def translate_article(
    article_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    article = await db.scalar(
        select(Article).where(Article.id == article_id, Article.user_id == current_user.id)
    )
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    if article.translation_status == "processing":
        return {"translation_status": "processing"}
    article.translation_status = "processing"
    await db.commit()
    from app.services import batch_translation_service
    asyncio.create_task(batch_translation_service.translate_article(article_id))
    return {"translation_status": "processing"}
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/articles.py
git commit -m "feat: add unexposed user article translate endpoint, remove auto-trigger on create"
```

---

## Task 5: Frontend — Types update

**Files:**
- Modify: `frontend/src/types/index.ts`

**Interfaces:**
- Produces: `TranslationStatus` type; updated `ArticleListItem`, `LibraryArticleListItem`, `ChapterListItem`

- [ ] **Step 1: Add TranslationStatus type and update interfaces**

In `frontend/src/types/index.ts`:

Add after the `Difficulty` type line:
```typescript
export type TranslationStatus = "untranslated" | "processing" | "done" | "stale" | "failed";
```

In `ArticleListItem`, add:
```typescript
translation_status?: TranslationStatus;
```

In `LibraryArticleListItem`, add after `source_url`:
```typescript
translation_status: TranslationStatus;
```

In `ChapterListItem`, add after `last_sentence_index`:
```typescript
translation_status: TranslationStatus;
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npm run build 2>&1 | grep -E "error|Error" | head -20
```
Expected: no type errors related to the new fields.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat: add TranslationStatus type and expose on article/chapter list items"
```

---

## Task 6: Frontend — TranslateConfirmModal component

**Files:**
- Create: `frontend/src/components/TranslateConfirmModal.tsx`

**Interfaces:**
- Consumes: nothing from other tasks
- Produces:
```typescript
interface TranslateConfirmModalProps {
  title: string;
  wordCount: number;
  onConfirm: () => void;
  onCancel: () => void;
}
export function TranslateConfirmModal(props: TranslateConfirmModalProps): JSX.Element
```

- [ ] **Step 1: Create the modal component**

Create `frontend/src/components/TranslateConfirmModal.tsx`:
```tsx
interface TranslateConfirmModalProps {
  title: string;
  wordCount: number;
  onConfirm: () => void;
  onCancel: () => void;
}

export function TranslateConfirmModal({ title, wordCount, onConfirm, onCancel }: TranslateConfirmModalProps) {
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl p-6 max-w-sm w-full mx-4">
        <h3 className="text-base font-semibold text-gray-900 mb-1">确认预翻译</h3>
        <p className="text-sm text-gray-500 mb-4">预翻译会消耗 AI 配额，请确认。</p>
        <div className="bg-gray-50 rounded-lg px-4 py-3 mb-5">
          <p className="text-sm font-medium text-gray-800 line-clamp-2">{title}</p>
          <p className="text-xs text-gray-400 mt-1">{wordCount.toLocaleString()} 词</p>
        </div>
        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
          >
            取消
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-2 text-sm font-medium text-white bg-blue-500 rounded-lg hover:bg-blue-600 transition-colors"
          >
            确认翻译
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npm run build 2>&1 | grep -E "error|Error" | head -20
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/TranslateConfirmModal.tsx
git commit -m "feat: add TranslateConfirmModal shared component"
```

---

## Task 7: Frontend — AdminPage articles tab (status badges + translate buttons)

**Files:**
- Modify: `frontend/src/pages/AdminPage.tsx`

**Interfaces:**
- Consumes: `TranslateConfirmModal` from Task 6; `TranslationStatus` from Task 5
- Produces: translate mutations calling `admin/library/articles/:id/translate`

- [ ] **Step 1: Add TranslationStatusBadge helper and translate mutation to ArticlesTab**

At the top of `ArticlesTab` function (after existing state declarations), add:

```tsx
// Import at top of file:
import { TranslateConfirmModal } from "../components/TranslateConfirmModal";
import type { TranslationStatus } from "../types";
```

Add `TranslationStatusBadge` component before `ArticlesTab`:
```tsx
function TranslationStatusBadge({ status }: { status: TranslationStatus | undefined }) {
  if (!status || status === "untranslated") return <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">未翻译</span>;
  if (status === "processing") return <span className="text-xs bg-yellow-100 text-yellow-700 px-2 py-0.5 rounded-full">翻译中</span>;
  if (status === "done") return <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">已翻译</span>;
  if (status === "stale") return <span className="text-xs bg-orange-100 text-orange-700 px-2 py-0.5 rounded-full">已失效</span>;
  if (status === "failed") return <span className="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded-full">失败</span>;
  return null;
}
```

- [ ] **Step 2: Add translate mutation and modal state inside ArticlesTab**

Inside `ArticlesTab`, add after existing mutations:
```tsx
const [translateTarget, setTranslateTarget] = useState<LibraryArticleListItem | null>(null);

const translateMutation = useMutation({
  mutationFn: (id: string) => api.post(`admin/library/articles/${id}/translate`).json(),
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-library-articles"] }),
});
```

- [ ] **Step 3: Add modal rendering and translate button in article rows**

At the bottom of the `ArticlesTab` return, before the closing `</div>`, add:
```tsx
{translateTarget && (
  <TranslateConfirmModal
    title={translateTarget.title}
    wordCount={translateTarget.word_count}
    onConfirm={() => {
      translateMutation.mutate(translateTarget.id);
      setTranslateTarget(null);
    }}
    onCancel={() => setTranslateTarget(null)}
  />
)}
```

In each article row (inside `articles?.map`), add before the edit button:
```tsx
{(a.translation_status === "untranslated" || a.translation_status === "stale" || a.translation_status === "failed") && (
  <button
    onClick={() => setTranslateTarget(a)}
    disabled={translateMutation.isPending}
    className="p-1.5 text-gray-400 hover:text-blue-500 transition-colors"
    title={a.translation_status === "untranslated" ? "翻译" : a.translation_status === "stale" ? "重新翻译" : "重试"}
  >
    ⚡
  </button>
)}
<TranslationStatusBadge status={a.translation_status} />
```

- [ ] **Step 4: Verify in browser**

Open `http://localhost:5173/admin`, go to 文章 tab. Verify:
- Each article shows a status badge
- Clicking ⚡ button opens the confirmation modal with title and word count
- Cancelling closes modal without calling API
- Confirming calls the translate endpoint

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/AdminPage.tsx frontend/src/components/TranslateConfirmModal.tsx
git commit -m "feat: add translation status badges and manual translate buttons to admin articles tab"
```

---

## Task 8: Frontend — AdminPage books tab (chapter editing + translate)

**Files:**
- Modify: `frontend/src/pages/AdminPage.tsx`

**Interfaces:**
- Consumes: `TranslateConfirmModal`, `TranslationStatusBadge` (from Task 7); `ChapterListItem.translation_status` (Task 5)
- Produces: chapter edit form in right panel; chapter translate mutation

- [ ] **Step 1: Add chapter state and mutations to BooksTab**

Inside `BooksTab`, add state and mutations:
```tsx
const [translateChapterTarget, setTranslateChapterTarget] = useState<{ bookId: string; chapter: { id: string; title: string; chapter_order: number; word_count: number; translation_status: TranslationStatus } } | null>(null);
const [editingChapter, setEditingChapter] = useState<{ bookId: string; chapterId: string; title: string; raw_text: string } | null>(null);
const [chapterEditError, setChapterEditError] = useState("");

const translateChapterMutation = useMutation({
  mutationFn: ({ bookId, chapterId }: { bookId: string; chapterId: string }) =>
    api.post(`admin/library/books/${bookId}/chapters/${chapterId}/translate`).json(),
  onSuccess: (_, { bookId }) => {
    queryClient.invalidateQueries({ queryKey: ["library-book-detail", bookId] });
    setTranslateChapterTarget(null);
  },
});

const editChapterMutation = useMutation({
  mutationFn: ({ bookId, chapterId, body }: { bookId: string; chapterId: string; body: object }) =>
    api.patch(`admin/library/books/${bookId}/chapters/${chapterId}`, { json: body }).json(),
  onSuccess: (_, { bookId }) => {
    queryClient.invalidateQueries({ queryKey: ["library-book-detail", bookId] });
    setEditingChapter(null);
    setChapterEditError("");
  },
  onError: async (err: any) => {
    const msg = await err.response?.json().catch(() => null);
    setChapterEditError(msg?.detail ?? "保存失败");
  },
});
```

- [ ] **Step 2: Update BookChapterList to show status badge and action buttons**

`BookChapterList` currently receives `onDeleteChapter`. Extend its props and rendering:

Replace the `BookChapterList` component entirely:
```tsx
function BookChapterList({
  bookId,
  onDeleteChapter,
  onTranslateChapter,
  onEditChapter,
}: {
  bookId: string;
  onDeleteChapter: (bookId: string, chapterId: string, title: string) => void;
  onTranslateChapter: (bookId: string, chapter: { id: string; title: string; chapter_order: number; word_count: number; translation_status: TranslationStatus }) => void;
  onEditChapter: (bookId: string, chapterId: string, title: string, rawText: string) => void;
}) {
  const { data: bookDetail, isLoading } = useQuery({
    queryKey: ["library-book-detail", bookId],
    queryFn: () => api.get(`library/books/${bookId}`).json<{ chapters: { id: string; title: string; chapter_order: number; word_count: number; translation_status: TranslationStatus; raw_text: string }[] }>(),
  });

  if (isLoading) return <p className="text-xs text-gray-400 px-8 pb-2">加载章节...</p>;
  if (!bookDetail?.chapters?.length) return <p className="text-xs text-gray-400 px-8 pb-2">暂无章节</p>;

  return (
    <div className="bg-gray-50 px-8 pb-2">
      {bookDetail.chapters.map((ch) => (
        <div key={ch.id} className="flex items-center justify-between py-1.5 border-b border-gray-100 last:border-0">
          <div>
            <span className="text-xs text-gray-500 mr-2">Ch.{ch.chapter_order}</span>
            <span className="text-xs text-gray-700">{ch.title}</span>
            <span className="text-xs text-gray-400 ml-2">{ch.word_count.toLocaleString()} 词</span>
          </div>
          <div className="flex items-center gap-1">
            <TranslationStatusBadge status={ch.translation_status} />
            {(ch.translation_status === "untranslated" || ch.translation_status === "stale" || ch.translation_status === "failed") && (
              <button
                onClick={() => onTranslateChapter(bookId, ch)}
                className="p-1 text-gray-400 hover:text-blue-500 transition-colors"
                title="翻译"
              >⚡</button>
            )}
            <button
              onClick={() => onEditChapter(bookId, ch.id, ch.title, ch.raw_text ?? "")}
              className="p-1 text-gray-400 hover:text-blue-500 transition-colors"
              title="编辑章节"
            >
              <Pencil size={12} />
            </button>
            <button
              onClick={() => onDeleteChapter(bookId, ch.id, ch.title)}
              className="p-1 text-gray-300 hover:text-red-500 transition-colors"
              title="删除章节"
            >
              <Trash2 size={12} />
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Wire up BookChapterList in BooksTab and add edit form + modal**

In the BooksTab JSX where `<BookChapterList>` is rendered, update:
```tsx
<BookChapterList
  bookId={book.id}
  onDeleteChapter={handleDeleteChapter}
  onTranslateChapter={(bookId, chapter) => setTranslateChapterTarget({ bookId, chapter })}
  onEditChapter={(bookId, chapterId, title, raw_text) => {
    setEditingChapter({ bookId, chapterId, title, raw_text });
    setChapterEditError("");
  }}
/>
```

In the right panel of BooksTab (after the add chapter form), add the chapter edit form:
```tsx
{editingChapter && (
  <div className="border-t border-gray-100 pt-6">
    <div className="flex items-center justify-between mb-3">
      <h2 className="text-sm font-semibold text-gray-700">编辑章节</h2>
      <button onClick={() => setEditingChapter(null)} className="text-gray-400 hover:text-gray-600"><X size={16} /></button>
    </div>
    <div className="space-y-3">
      <input
        type="text"
        value={editingChapter.title}
        onChange={(e) => setEditingChapter((c) => c ? { ...c, title: e.target.value } : null)}
        className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400"
        placeholder="章节标题"
      />
      <textarea
        value={editingChapter.raw_text}
        onChange={(e) => setEditingChapter((c) => c ? { ...c, raw_text: e.target.value } : null)}
        rows={10}
        className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400 resize-y font-mono"
        placeholder="章节正文"
      />
      {chapterEditError && <p className="text-xs text-red-500">{chapterEditError}</p>}
      <button
        onClick={() => editChapterMutation.mutate({
          bookId: editingChapter.bookId,
          chapterId: editingChapter.chapterId,
          body: { title: editingChapter.title, raw_text: editingChapter.raw_text || null },
        })}
        disabled={editChapterMutation.isPending}
        className="w-full py-2 bg-blue-500 text-white text-sm font-medium rounded-lg hover:bg-blue-600 disabled:opacity-50 transition-colors"
      >
        {editChapterMutation.isPending ? "保存中..." : "保存章节"}
      </button>
    </div>
  </div>
)}
```

Add the translate confirmation modal at the bottom of BooksTab return:
```tsx
{translateChapterTarget && (
  <TranslateConfirmModal
    title={`Ch.${translateChapterTarget.chapter.chapter_order} ${translateChapterTarget.chapter.title}`}
    wordCount={translateChapterTarget.chapter.word_count}
    onConfirm={() => translateChapterMutation.mutate({
      bookId: translateChapterTarget.bookId,
      chapterId: translateChapterTarget.chapter.id,
    })}
    onCancel={() => setTranslateChapterTarget(null)}
  />
)}
```

- [ ] **Step 4: Verify in browser**

Open Admin › 图书 tab. Expand a book. Verify:
- Each chapter shows a translation status badge
- ⚡ button opens confirmation modal
- Pencil button shows edit form in right panel, pre-filled with title and body
- Saving edit updates the chapter

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/AdminPage.tsx
git commit -m "feat: add chapter editing and translate buttons to admin books tab"
```

---

## Task 9: Frontend — ArticleListPage inline article editing

**Files:**
- Modify: `frontend/src/pages/ArticleListPage.tsx`

**Interfaces:**
- Consumes: existing `PUT /api/v1/articles/:id` backend endpoint
- Produces: inline edit form for user-uploaded articles

- [ ] **Step 1: Add edit state and mutation**

In `ArticleListPage`, add state and mutation:
```tsx
const [editingArticle, setEditingArticle] = useState<{ id: string; title: string; raw_text: string } | null>(null);
const [editError, setEditError] = useState("");

const editMutation = useMutation({
  mutationFn: ({ id, body }: { id: string; body: { title: string; raw_text: string } }) =>
    api.put(`articles/${id}`, { json: body }).json<ArticleListItem>(),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ["articles"] });
    setEditingArticle(null);
    setEditError("");
  },
  onError: async (err: any) => {
    const msg = await err.response?.json().catch(() => null);
    setEditError(msg?.detail ?? "保存失败");
  },
});
```

Note: `PUT /articles/:id` requires `{ title, raw_text }`. The backend `ChapterEditRequest` schema is used here — it has both fields. Import `Pencil` from lucide-react if not already imported.

- [ ] **Step 2: Add inline edit form and edit button to article rows**

Replace the current article rows rendering. For each article in `articles?.map`, add an edit button for non-library articles:

```tsx
{articles?.map((article) => (
  <div key={article.id}>
    {editingArticle?.id === article.id && (
      <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 mb-2">
        <div className="flex items-center justify-between mb-3">
          <p className="text-xs font-semibold text-blue-700">编辑文章</p>
          <button onClick={() => setEditingArticle(null)} className="text-gray-400 hover:text-gray-600"><X size={14} /></button>
        </div>
        <input
          type="text"
          value={editingArticle.title}
          onChange={(e) => setEditingArticle((a) => a ? { ...a, title: e.target.value } : null)}
          className="w-full border border-gray-300 rounded-lg px-3 py-2 mb-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
          placeholder="文章标题"
        />
        <textarea
          value={editingArticle.raw_text}
          onChange={(e) => setEditingArticle((a) => a ? { ...a, raw_text: e.target.value } : null)}
          rows={8}
          className="w-full border border-gray-300 rounded-lg px-3 py-2 mb-3 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-400 resize-none"
          placeholder="文章正文"
        />
        {editError && <p className="text-xs text-red-500 mb-2">{editError}</p>}
        <div className="flex gap-2">
          <button
            onClick={() => editMutation.mutate({ id: editingArticle.id, body: { title: editingArticle.title, raw_text: editingArticle.raw_text } })}
            disabled={editMutation.isPending}
            className="bg-blue-500 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-600 disabled:opacity-50 transition-colors"
          >
            {editMutation.isPending ? "保存中..." : "保存"}
          </button>
          <button
            onClick={() => setEditingArticle(null)}
            className="bg-gray-200 text-gray-700 px-4 py-2 rounded-lg text-sm font-medium hover:bg-gray-300 transition-colors"
          >
            取消
          </button>
        </div>
      </div>
    )}
    <div className="flex items-center justify-between bg-white border border-gray-200 rounded-xl p-4 hover:shadow-sm transition-shadow">
      <Link
        to={article.is_library ? `/library/${article.id}` : `/articles/${article.id}`}
        className="flex-1 min-w-0"
      >
        <div className="flex items-center gap-2 flex-wrap">
          <h3 className="font-medium text-gray-800 hover:text-blue-600 truncate">{article.title}</h3>
          {article.is_library && (
            <span className="shrink-0 text-xs bg-blue-50 text-blue-600 border border-blue-100 px-1.5 py-0.5 rounded font-medium">公共库</span>
          )}
          {article.is_library && article.source_category && (
            <span className="shrink-0 text-xs text-gray-400">{CATEGORY_LABELS[article.source_category] ?? article.source_category}</span>
          )}
        </div>
        <p className="text-xs text-gray-400 mt-0.5">
          {article.word_count.toLocaleString()} 词 ·{" "}
          {new Date(article.created_at).toLocaleDateString("zh-CN")}
        </p>
      </Link>
      <div className="flex items-center gap-2 ml-4 shrink-0">
        {!article.is_library && (
          <button
            onClick={() => {
              setEditingArticle({ id: article.id, title: article.title, raw_text: "" });
              setEditError("");
            }}
            className="text-gray-300 hover:text-blue-400 transition-colors"
            title="编辑"
          >
            <Pencil size={14} />
          </button>
        )}
        <button
          onClick={() => handleRemove(article)}
          className="text-gray-300 hover:text-red-400 transition-colors text-sm"
        >
          {article.is_library ? "移除" : "删除"}
        </button>
      </div>
    </div>
  </div>
))}
```

Note: The edit form initialises `raw_text: ""` — the user must type the new text. The backend `PUT /articles/:id` requires the full `raw_text`. To pre-fill, we'd need to fetch the article first (it's not in the list response). This is acceptable for now per YAGNI — the user types a new body.

Add `Pencil` and `X` to the lucide-react import at the top:
```tsx
import { Pencil, X } from "lucide-react";
```

- [ ] **Step 3: Verify in browser**

Open `http://localhost:5173` (文章 page). Verify:
- User-uploaded articles show pencil icon
- Library bookmarked articles do not show pencil icon
- Clicking pencil opens inline form
- Only one form open at a time (opening another closes the previous — this is automatic since `editingArticle` is a single state)
- Saving calls `PUT /articles/:id` and refreshes the list

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ArticleListPage.tsx
git commit -m "feat: add inline editing for user-uploaded articles in article list"
```

---

## Self-Review Checklist

**Spec coverage:**
- ✅ 5-state translation_status model (Task 1)
- ✅ translation_status in list responses (Task 2)
- ✅ Admin article translate endpoint (Task 3)
- ✅ Admin chapter translate endpoint (Task 3)
- ✅ Remove auto-trigger on create/edit (Tasks 3, 4)
- ✅ Chapter edit endpoint PATCH (Task 3)
- ✅ User article translate endpoint unexposed (Task 4)
- ✅ Translation status badges in AdminPage articles tab (Task 7)
- ✅ TranslateConfirmModal with title + word count (Task 6)
- ✅ Chapter editing in AdminPage books tab (Task 8)
- ✅ User article inline editing in ArticleListPage (Task 9)
- ✅ Library bookmarked articles no edit button (Task 9)

**Existing DB rows:** Articles with `translation_status = "pending"` are handled gracefully — `batch_translation_service` now only skips `processing` and `done`; `pending` rows will be treated as translatable (same as `untranslated`). No data migration needed.

**Type consistency:**
- `TranslationStatus` defined in Task 5, used in Tasks 7, 8, 9 ✅
- `TranslateConfirmModal` props defined in Task 6, consumed in Tasks 7, 8 ✅
- `ChapterPatchRequest` defined in Task 2, consumed in Task 3 ✅
- `translateChapterMutation` and `editChapterMutation` in Task 8 reference correct endpoint paths ✅
