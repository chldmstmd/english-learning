# 技术设计文档

**项目名称：** Context Translation Layer  
**对应 PRD：** `prd.md`  
**当前范围：** 浏览器插件优先；Web reader 仅保留为最小测试壳。

---

## 1. 架构

```
Browser Extension / Web Reader
        |
        | REST + JWT
        v
FastAPI API
        |
        +-- spaCy tokenization
        +-- DeepSeek context translation
        +-- Free translation fallback
        v
PostgreSQL
```

核心原则：

- 翻译层是产品主体，阅读器只是文本容器。
- 用户实际点击结果存于位置级 `article_annotations`。
- 预翻译结果存于位置级 `article_translations` cache。
- 同一个 lemma 在不同句子位置可以有不同翻译。

---

## 2. 数据模型

### `users`

- `id`
- `email`
- `hashed_password`
- `created_at`

### `articles`

最小 Web reader 的文本容器。

- `id`
- `user_id`
- `title`
- `raw_text`
- `tokens`
- `sentences`
- `word_count`
- `translation_status`
- `created_at`

### `article_annotations`

位置级语境翻译。

- `article_id`
- `user_id`
- `word`
- `sentence_index`
- `word_index`
- `translation`
- `source_sentence`
- `is_fallback`
- `gen_status`
- `is_stale`

唯一约束：`(article_id, user_id, sentence_index, word_index)`。

### `article_translations`

批量预翻译缓存。

- `article_id`
- `sentence_index`
- `word_index`
- `word`
- `lemma`
- `translation`

唯一约束：`(article_id, sentence_index, word_index)`。

---

## 3. API

### Auth

- `POST /auth/register`
- `POST /auth/login`
- `GET /auth/me`

### Articles

- `POST /api/v1/articles`
- `GET /api/v1/articles`
- `GET /api/v1/articles/{article_id}`
- `DELETE /api/v1/articles/{article_id}`
- `PUT /api/v1/articles/{article_id}/progress`
- `POST /api/v1/articles/{article_id}/translate`

Article endpoints are scoped to `current_user.id`.

### Translation

`POST /api/v1/translate-word`

Request:

```json
{
  "word": "banks",
  "lemma": "bank",
  "sentence": "The banks of the river flooded.",
  "article_id": "uuid",
  "sentence_index": 0,
  "word_index": 2
}
```

Flow:

1. Verify the article belongs to the current user.
2. Check `article_translations` for the clicked position.
3. If no cache hit, call context translation.
4. Fallback to free translation when enabled.
5. Upsert `article_annotations` for the clicked position.
6. Return translation.

---

## 4. Frontend

Current Web reader routes:

- `/login`
- `/register`
- `/`
- `/articles/:id`

Key components:

- `ArticleListPage`: minimal paste-text container list.
- `ArticleReaderPage`: renders tokenized text.
- `WordToken`: click handling and annotation display.
- `WordSidebar`: current word, context translation, and source sentence.

State:

- Zustand stores auth, sidebar state, and annotations.
- React Query handles API request caching and invalidation.

---

## 5. Browser Extension Direction

The extension should reuse the same core API:

1. Content script detects clicked English word.
2. Extracts the local sentence or paragraph.
3. Sends `word`, `lemma`, and context to the API.
4. Renders inline translation near the word.
5. Uses the same realtime translation and pretranslation cache model as the Web reader.

The extension may not have an `article_id` in the long term. When implementing that path, introduce a dedicated endpoint or lightweight document/session identifier instead of expanding the Web reader into a content platform.

---

## 6. Boundary

This branch keeps only the translation layer and the minimal Web reader shell. Reading-platform code and documents are intentionally absent.
