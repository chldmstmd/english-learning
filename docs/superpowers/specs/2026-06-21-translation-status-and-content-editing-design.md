# Translation Status & Content Editing Design

**Date:** 2026-06-21  
**Scope:** Manual translation triggering, translation status model, chapter editing, user article editing

---

## Overview

Replace the current auto-triggered batch translation with explicit admin-controlled translation per article/chapter. Add a five-state translation status model. Add editing UI for library chapters and user-uploaded articles.

---

## 1. Translation Status Model

`Article.translation_status` changes from `pending | processing | done | failed` to:

| Value | Meaning |
|-------|---------|
| `untranslated` | Never been translated |
| `processing` | Translation job running in background |
| `done` | Translation complete and in sync with current `raw_text` |
| `stale` | `raw_text` was edited after translation; cache is invalid |
| `failed` | Last translation job errored; retry available |

**State transitions:**
- Article/chapter created → `untranslated`
- Admin/user edits `raw_text` → `stale` + existing `article_translations` rows deleted
- Translation triggered → immediately `processing`, then `done` or `failed` on completion
- Translation was `done` and `raw_text` is edited again → `stale`

**Existing articles in DB:** On deploy, articles currently in `pending` state become `untranslated`; `done` stays `done`; `failed` stays `failed`. The old `processing` state is treated as `failed` (the worker is not running).

---

## 2. API Changes

### New endpoints

```
POST /api/v1/admin/library/articles/:id/translate
POST /api/v1/admin/library/books/:book_id/chapters/:chapter_id/translate
POST /api/v1/articles/:id/translate        ← exists in backend, not exposed to users yet
```

All three: set `translation_status = "processing"`, fire background task, return `{ translation_status: "processing" }`. Idempotent: calling again while `processing` returns 200 without re-queuing.

### New chapter edit endpoint

```
PATCH /api/v1/admin/library/books/:book_id/chapters/:chapter_id
Body: { title?: string, raw_text?: string }
```

Same logic as article PATCH: if `raw_text` provided, re-tokenize, reset status to `stale`, delete old translations.

### translation_status exposed in list responses

- `LibraryArticleListItem` → add `translation_status: str`
- `ArticleListItem` → add `translation_status: str` (for admin view; not shown in user-facing UI)
- `ChapterListItem` → add `translation_status: str`

---

## 3. Admin UI — Articles Tab

Each article row in AdminPage articles list gains:

- **Status badge + action** per state:
  - `untranslated` → gray "未翻译" + "翻译" button (blue outline)
  - `processing` → yellow "翻译中", no button (disabled state)
  - `done` → green "已翻译", no translate button
  - `stale` → orange "已失效" + "重新翻译" button
  - `failed` → red "失败" + "重试" button

- **Translate button** triggers a custom confirmation modal (see §5) before firing the API call.

Auto-triggering translation on article create/edit is removed.

---

## 4. Admin UI — Books Tab (Chapter Editing)

Each chapter row (when book is expanded) gains:

- **Status badge** same as above
- **翻译 / 重新翻译 / 重试** button (with confirmation modal)
- **编辑** button: clicks open the right-side form panel pre-filled with chapter title and `raw_text`. Saving calls `PATCH /admin/library/books/:id/chapters/:chapter_id`.

---

## 5. Translation Confirmation Modal

Triggered whenever a translate/re-translate/retry button is clicked. Displays:

- Article/chapter title
- Word count
- Warning: "预翻译会消耗 AI 配额，请确认。"
- Two buttons: **确认翻译** (primary) / **取消**

Implemented as a shared React component `<TranslateConfirmModal>` used across both articles and chapters tabs.

---

## 6. User Article Editing (ArticleListPage)

Each user-uploaded article row gains an **✏ 编辑** button. Clicking expands an inline form above that row (only one open at a time) with:

- Title input (pre-filled)
- `raw_text` textarea (pre-filled)
- **保存** / **取消** buttons

Saving calls existing `PUT /api/v1/articles/:id`. Library bookmarked articles do not show the edit button.

`translation_status` for user articles is not shown in the UI (reserved for future use).

---

## 7. Out of Scope

- User-facing translation trigger UI (backend endpoint exists but not exposed)
- Bulk translate all articles
- Translation cost estimation or quota tracking
