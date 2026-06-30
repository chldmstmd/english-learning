# Paragraph Version Articles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace article-position pretranslation cache with paragraph-version cache so unchanged paragraphs keep translations across edits.

**Architecture:** Add immutable paragraph versions, article paragraph links, paragraph-level translation cache, and paragraph-occurrence annotations. Keep existing article status/progress fields and expose ordered paragraphs to the frontend.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL JSONB, React, TanStack Query, Zustand.

---

### Task 1: Backend Models And Services

**Files:**
- Create: `backend/app/models/paragraph.py`
- Create: `backend/app/services/paragraph_service.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/services/schema_service.py`

- [ ] Add paragraph-version, article-paragraph, paragraph-translation, and paragraph-annotation ORM models.
- [ ] Add helpers to split text into paragraphs, create/reuse paragraph versions by exact text hash, update article paragraph links, and compute translation progress.
- [ ] Import the new models during app startup.

### Task 2: Article APIs

**Files:**
- Modify: `backend/app/schemas/article.py`
- Modify: `backend/app/routers/articles.py`

- [ ] Create article rows with ordered paragraph links.
- [ ] Return ordered paragraphs in article detail responses.
- [ ] Add `PUT /api/v1/articles/{article_id}` to edit title/text and preserve unchanged paragraph-version translations.
- [ ] Delete paragraph links and new annotation/cache rows when deleting an article.

### Task 3: Translation APIs

**Files:**
- Modify: `backend/app/schemas/translate.py`
- Modify: `backend/app/routers/translate.py`
- Modify: `backend/app/services/annotation_service.py`
- Modify: `backend/app/services/batch_translation_service.py`

- [ ] Make word translation requests include `article_paragraph_id`.
- [ ] Read pretranslation cache from `paragraph_translations`.
- [ ] Store click annotations by article paragraph occurrence.
- [ ] Batch translate current paragraph versions and skip existing paragraph-version cache rows.

### Task 4: Frontend

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/store/annotationStore.ts`
- Modify: `frontend/src/components/ArticleBody.tsx`
- Modify: `frontend/src/components/WordToken.tsx`
- Modify: `frontend/src/pages/ArticleReaderPage.tsx`

- [ ] Render ordered article paragraphs.
- [ ] Key annotations by article paragraph id and local token position.
- [ ] Send `article_paragraph_id` in translate requests.
- [ ] Add a minimal edit/save/cancel flow in the reader.

### Task 5: Verification

**Files:**
- Create: `backend/tests/test_paragraph_articles.py`
- Modify existing affected backend tests.

- [ ] Run paragraph-focused backend tests.
- [ ] Run backend translation/cache tests.
- [ ] Run frontend build.
