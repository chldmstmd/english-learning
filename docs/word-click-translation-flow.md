# 单词点击翻译 — 完整链路

## 一、前端流程

### 1. 用户点击（WordToken.tsx）

用户点击 `<ruby>` 元素，触发 `handleClick()`：

- **unseen / mastered 状态** → 调用 `translateMutation.mutate()`
- **new 状态** → 更新为 "reviewing"
- **reviewing 状态** → 打开侧边栏

### 2. 发起请求

```ts
// WordToken.tsx:33-62
api.post("translate-word", {
  json: {
    word: token.text,           // 原文形式，如 "banks"
    lemma: token.lemma,         // 词元，如 "bank"
    sentence: getSentenceText(),// 上下文句子
    article_id: articleId,
    sentence_index: token.sentence_index,
    word_index: token.index,
  }
})
```

**乐观更新**：`onMutate` 立即将 wordStatus 设为 "new"（不等响应）

### 3. 响应处理（onSuccess）

- 更新 Zustand store 中的 wordStatus
- 存储 annotation（translation、source_sentence、is_fallback、gen_status）
- UI 重渲染，`<rt>` 标签显示中文翻译

### 4. 侧边栏（WordSidebar.tsx）

若开启 `autoOpenSidebar`，额外请求 `GET /vocab/{lemma}/detail?sentence=...`，获取：
- 音标 + 词典释义（Free Dictionary API）
- AI 语境分析（Gemini）

---

## 二、后端流程

### 1. 路由入口（routers/translate.py:30-97）

`POST /api/v1/translate-word`

```
验证文章访问权限
    ↓
upsert_word → 创建/获取词汇条目（status="new"）
    ↓
查询 batch translation 缓存（article_translations 表）
    ↓
缓存命中？→ 直接使用缓存翻译
缓存未命中？→ 调用 _get_translation_with_fallback()
    ↓
upsert_annotation → 存储翻译结果到 article_annotations 表
    ↓
提交事务
    ↓
后台任务：sync_word_to_user_articles_task()（同步到其他文章）
    ↓
返回 TranslateResponse
```

### 2. 翻译获取（_get_translation_with_fallback）

```python
# translate.py:16-27
try:
    translation = await ai_service.translate_in_context(word, sentence)
    is_fallback = False
except:
    translation = await free_translation_service.translate(word)
    is_fallback = True
```

### 3. AI 翻译服务（services/ai_service.py:101-117）

- **模型**：`gemini-3.1-flash-lite`
- **超时**：5 秒
- **温度**：0.1
- **Prompt**：
  ```
  你是专业英中词汇翻译助手。
  根据给定句子，为指定单词提供最符合当前语境的中文翻译。
  翻译控制在2-6个中文字以内。
  只返回JSON格式：{"translation": "翻译结果"}
  ```
- 解析 JSON 提取 `translation` 字段

### 4. Fallback 服务（services/free_translation_service.py）

- 使用 `deep_translator` 调用 Google Translate
- 英文 → 简体中文
- 在线程池中执行（阻塞 I/O）

### 5. 批量缓存机制

- 文章创建/同步时后台预翻译所有单词，存入 `article_translations` 表
- 按 `(article_id, sentence_index, word_index)` 索引
- 用户点击时优先命中缓存，避免重复调用 AI

---

## 三、数据流转图

```
用户点击 WordToken
    │
    ▼ (乐观更新 status → "new")
POST /translate-word
    │
    ├─ 验证权限
    ├─ upsert vocabulary (status="new")
    ├─ 查 article_translations 缓存
    │   ├─ 命中 → translation, is_fallback=False
    │   └─ 未命中 → Gemini AI (fallback: Google Translate)
    ├─ upsert article_annotation (gen_status="done")
    ├─ 后台: 同步到用户其他文章
    │
    ▼
TranslateResponse {word, lemma, translation, is_fallback, status}
    │
    ▼
前端更新 Zustand store → UI 渲染 <rt>翻译</rt>
    │
    ▼ (若开启侧边栏)
GET /vocab/{lemma}/detail
    ├─ Free Dictionary API → 音标 + 释义
    └─ Gemini AI → 语境分析
    │
    ▼
WordSidebar 显示完整词汇信息
```

---

## 四、状态生命周期

```
unseen ──[点击]──→ new ──[点击]──→ reviewing ──[掌握]──→ mastered
  ↑                                                          │
  └────────────────────[点击已掌握单词]─────────────────────────┘
```

---

## 五、关键设计点

| 特性 | 说明 |
|------|------|
| 乐观更新 | 点击即显示状态变化，失败回滚 |
| 批量预翻译缓存 | 避免逐词调用 AI，降低延迟 |
| Fallback 链 | Gemini → Google Translate，保证可用性 |
| 跨文章同步 | 后台将新词同步到用户所有文章 |
| 轮询 pending | 前端每 2s 轮询未完成的翻译 |
| is_fallback 标记 | 前端用 `*` 标识非 AI 翻译结果 |

---

## 六、涉及的数据库表

### vocabulary

| 字段 | 说明 |
|------|------|
| word | 词元（每用户唯一） |
| status | "new" / "reviewing" / "mastered" |
| context_translation | 首次翻译结果 |
| source_sentence | 首次上下文句子 |

### article_annotations

| 字段 | 说明 |
|------|------|
| (article_id, user_id, word) | 唯一约束 |
| translation | 中文翻译 |
| is_fallback | 是否为 fallback 翻译 |
| gen_status | "pending" / "done" / "failed" |

### article_translations（批量缓存）

| 字段 | 说明 |
|------|------|
| (article_id, sentence_index, word_index) | 唯一约束 |
| lemma | 词元 |
| translation | 预翻译结果 |
