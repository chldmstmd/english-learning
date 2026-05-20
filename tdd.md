# 技术设计文档 (TDD)

**项目名称：** Context-Aware Smart Reader  
**版本：** V1.0  
**对应 PRD：** prd.md  
**日期：** 2026-04-12

---

## 目录

1. [系统架构总览](#1-系统架构总览)
2. [技术选型（完整库列表）](#2-技术选型完整库列表)
3. [数据库设计](#3-数据库设计)
4. [后端设计](#4-后端设计)
5. [前端设计](#5-前端设计)
6. [AI 集成设计](#6-ai-集成设计)
7. [关键业务流程](#7-关键业务流程)
8. [性能与可靠性设计](#8-性能与可靠性设计)
9. [可访问性实现](#9-可访问性实现)
10. [目录结构](#10-目录结构)

---

## 1. 系统架构总览

```
┌─────────────────────────────────────────────────────────┐
│                     Client (Browser)                    │
│   React + Tailwind │ Zustand │ React Query              │
└─────────────────────────┬───────────────────────────────┘
                          │ HTTPS / REST
┌─────────────────────────▼───────────────────────────────┐
│                  FastAPI Application                    │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────────┐ │
│  │  Router  │  │ Service  │  │  Background Tasks     │ │
│  │  Layer   │  │  Layer   │  │  (ARQ / asyncio)      │ │
│  └──────────┘  └──────────┘  └───────────────────────┘ │
│  ┌─────────────────────────────────────────────────────┐│
│  │            NLP Layer (spaCy)                        ││
│  └─────────────────────────────────────────────────────┘│
└─────────┬───────────────────────┬───────────────────────┘
          │                       │
┌─────────▼──────────┐  ┌────────▼─────────────────────┐
│   PostgreSQL 16    │  │   External APIs               │
│   (主数据库)        │  │   - OpenAI GPT-4o (翻译/解析) │
│                    │  │   - Free Dictionary API (词典) │
│                    │  │   - Web Speech API (TTS)      │
└────────────────────┘  └──────────────────────────────┘
```

**架构说明：**
- 无 Redis/缓存层（V1.0 规模下 PostgreSQL 足够，Post-MVP 可加）
- 后台异步翻译任务使用 Python `asyncio` + FastAPI `BackgroundTasks`，无需独立队列服务
- TTS 使用浏览器原生 Web Speech API，无需后端支持

---

## 2. 技术选型（完整库列表）

### 2.1 前端

| 类别 | 库 / 版本 | 用途 |
|------|-----------|------|
| 框架 | React 18 | UI 渲染 |
| 样式 | Tailwind CSS 3 | 原子化样式；单词状态颜色通过动态 class 控制 |
| 状态管理 | Zustand 4 | 轻量全局状态，管理词汇状态、侧边栏开关 |
| 服务端状态 | TanStack Query (React Query) 5 | API 请求缓存、后台刷新、乐观更新 |
| 路由 | React Router 6 | SPA 路由 |
| HTTP 客户端 | ky | 轻量 fetch 封装，支持超时控制 |
| 富文本 / 注音 | 原生 HTML `<ruby>` + CSS | 单词上方语境翻译展示 |
| 动画 | Framer Motion | 侧边栏滑入 / 底部抽屉动画 |
| 图标 | Lucide React | UI 图标 |
| 类型检查 | TypeScript 5 | 全量类型覆盖 |
| 构建 | Vite 5 | 开发/生产构建 |
| 测试 | Vitest + React Testing Library | 单元 & 组件测试 |

### 2.2 后端

| 类别 | 库 / 版本 | 用途 |
|------|-----------|------|
| Web 框架 | FastAPI 0.111 | REST API；原生支持 async |
| ASGI 服务器 | Uvicorn + Gunicorn | 生产部署 |
| ORM | SQLAlchemy 2 (async) | 数据库访问；使用 asyncpg 驱动 |
| 迁移 | Alembic | 数据库版本管理 |
| NLP | spaCy 3 (`en_core_web_sm`) | Tokenization + POS 标注 + 句子分割 |
| 数据校验 | Pydantic v2 | 请求/响应模型 |
| AI 客户端 | openai 1.x (Python SDK) | 调用 GPT-4o |
| 词典 API 客户端 | httpx | 调用 Free Dictionary API（降级） |
| 配置管理 | python-dotenv + Pydantic Settings | 环境变量管理 |
| 测试 | pytest + pytest-asyncio + httpx | 后端测试 |

### 2.3 数据库

| 类别 | 选型 | 说明 |
|------|------|------|
| 主库 | PostgreSQL 16 | JSONB 存储 Token 数组；GIN 索引支持 JSONB 查询 |
| 驱动 | asyncpg | 全异步 PostgreSQL 驱动 |

---

## 3. 数据库设计

### 3.1 表结构

#### `users`
```sql
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       TEXT NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

#### `articles`
```sql
CREATE TABLE articles (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    raw_text    TEXT NOT NULL,
    -- Token 数组: [{"text":"The","pos":"DT","index":0,"sentence_index":0}, ...]
    -- sentence_index 标记该 token 属于第几个句子，用于语境提取
    tokens      JSONB NOT NULL,
    -- 句子数组: [{"index":0,"text":"The bank of the river..."}, ...]
    sentences   JSONB NOT NULL,
    word_count  INTEGER NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_word_count CHECK (word_count <= 10000)
);

CREATE INDEX idx_articles_user_id ON articles(user_id);
CREATE INDEX idx_articles_tokens ON articles USING GIN (tokens);
```

> **设计说明：** `tokens` 中每个 token 增加 `sentence_index` 字段，使前端/后端在 O(1) 时间内定位句子，无需扫描。

#### `vocabulary`
```sql
CREATE TABLE vocabulary (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    word                TEXT NOT NULL,                  -- 统一小写原形
    pos                 TEXT,                           -- 词性（来自首次点击时的 spaCy 输出）
    context_translation TEXT,                           -- 入库时的语境翻译（可通过重新标红更新）
    source_sentence     TEXT,                           -- 触发标注的原始句子
    status              TEXT NOT NULL DEFAULT 'new'
                            CHECK (status IN ('new', 'reviewing', 'mastered')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    mastered_at         TIMESTAMPTZ,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Post-MVP: 间隔重复字段（V1.0 建表时预留，不使用）
    interval            INTEGER,
    ease_factor         REAL,
    next_review_at      TIMESTAMPTZ,
    UNIQUE (user_id, word)
);

CREATE INDEX idx_vocab_user_status ON vocabulary(user_id, status);
```

#### `article_annotations`
跨文章同步的核心表：每篇文章中每个已标注单词的**独立语境翻译**。

```sql
CREATE TABLE article_annotations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id      UUID NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    word            TEXT NOT NULL,                      -- 统一小写
    translation     TEXT,                               -- 该文章中的语境翻译
    source_sentence TEXT,                               -- 该文章中用于生成翻译的句子
    is_fallback     BOOLEAN NOT NULL DEFAULT FALSE,     -- TRUE 表示使用了词典降级翻译
    gen_status      TEXT NOT NULL DEFAULT 'pending'
                        CHECK (gen_status IN ('pending', 'done', 'failed')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (article_id, user_id, word)
);

CREATE INDEX idx_annotations_article ON article_annotations(article_id, user_id);
CREATE INDEX idx_annotations_word ON article_annotations(user_id, word);
```

> **设计说明：**  
> - `vocabulary` 存储词级全局状态（status）  
> - `article_annotations` 存储文章级翻译（per-article context translation）  
> - 两表通过 `user_id + word` 关联，无外键（word 不是 vocabulary 的唯一键以外的索引，用联合查询即可）  
> - 删除文章时，`ON DELETE CASCADE` 自动清除该文章的 annotations，不影响 vocabulary 记录

### 3.2 数据关系图

```
users ──< articles ──< article_annotations
  │                           │
  └────────< vocabulary >─────┘
          (user_id + word)
```

---

## 4. 后端设计

### 4.1 目录结构

```
backend/
├── app/
│   ├── main.py                 # FastAPI app 入口
│   ├── config.py               # Pydantic Settings 配置
│   ├── database.py             # SQLAlchemy async engine / session
│   ├── models/                 # SQLAlchemy ORM 模型
│   │   ├── user.py
│   │   ├── article.py
│   │   ├── vocabulary.py
│   │   └── annotation.py
│   ├── schemas/                # Pydantic 请求/响应模型
│   │   ├── article.py
│   │   ├── vocab.py
│   │   └── translate.py
│   ├── routers/                # FastAPI 路由
│   │   ├── articles.py
│   │   ├── vocab.py
│   │   └── translate.py
│   ├── services/               # 业务逻辑
│   │   ├── nlp_service.py      # spaCy tokenization
│   │   ├── ai_service.py       # GPT-4o 调用
│   │   ├── dict_service.py     # 词典 API 降级
│   │   ├── vocab_service.py    # 词汇状态管理
│   │   └── annotation_service.py  # 跨文章同步逻辑
│   └── background/
│       └── tasks.py            # FastAPI BackgroundTasks
├── alembic/                    # 数据库迁移
├── tests/
└── requirements.txt
```

### 4.2 API 接口详细设计

#### `POST /api/v1/articles` — 上传文章

**请求：**
```json
{
  "title": "string",
  "raw_text": "string"
}
```

**处理流程：**
1. 校验 `raw_text` 字数 ≤ 10,000（spaCy 计算）
2. 调用 `nlp_service.tokenize(raw_text)` 生成 tokens + sentences
3. 存入 `articles` 表
4. 查询该用户 vocabulary 中所有 `new` / `reviewing` / `mastered` 词
5. 为 vocabulary 中存在但 `article_annotations` 中无记录的词创建 `pending` 状态的 annotation 记录
6. 返回文章数据（含现有 annotations，`pending` 词的 translation 为 null）

**响应：**
```json
{
  "id": "uuid",
  "title": "string",
  "tokens": [...],
  "sentences": [...],
  "annotations": {
    "bank": { "translation": "河岸", "is_fallback": false, "gen_status": "done" }
  }
}
```

---

#### `GET /api/v1/articles/{article_id}` — 获取文章（含注解）

**处理流程：**
1. 查询文章基本信息
2. 查询该文章所有 `article_annotations`（已生成 + pending）
3. 对 `gen_status = pending` 的词，**触发后台翻译任务**（`BackgroundTasks.add_task`）
4. 立即返回（pending 词的 translation = null，前端 polling 或 SSE 获取结果）

**轮询机制（V1.0 简化方案）：**  
前端每 2 秒对 `pending` 词调用 `GET /api/v1/articles/{id}/annotations?words=bank,access`，直到全部 `done`。Post-MVP 可改为 SSE。

---

#### `POST /api/v1/translate-word` — 语境翻译（核心接口）

**请求：**
```json
{
  "word": "bank",
  "sentence": "The bank of the river flooded last night.",
  "article_id": "uuid"
}
```

**处理流程：**
1. 超时控制：3 秒，超时则走降级路径
2. 调用 `ai_service.translate_in_context(word, sentence)`
3. 若 AI 成功：更新 `article_annotations.translation`，`gen_status = done`
4. 若 AI 超时/失败：调用 `dict_service.get_definition(word)` 获取通用释义，`is_fallback = true`
5. 若 vocabulary 中无该词记录：INSERT INTO vocabulary（status = 'new'）
6. 触发 `annotation_service.sync_to_other_articles(user_id, word)`（后台）

**响应：**
```json
{
  "word": "bank",
  "translation": "河岸",
  "is_fallback": false,
  "status": "new"
}
```

---

#### `PATCH /api/v1/vocab/{word}/status` — 更新单词状态

**请求：**
```json
{ "status": "reviewing" }
```

**状态转换校验（服务层实现）：**

```python
VALID_TRANSITIONS = {
    "new": ["reviewing"],
    "reviewing": ["mastered"],
    "mastered": ["new"],
}
```

若 `status = mastered`，额外写入 `mastered_at = now()`。  
始终更新 `updated_at = now()`。

---

#### `GET /api/v1/vocab` — 获取生词表

支持筛选参数：`?status=new&status=reviewing&page=1&size=50`

---

#### `GET /api/v1/vocab/{word}/detail` — 词汇详情（侧边栏使用）

**响应：**
```json
{
  "word": "bank",
  "phonetic": "/bæŋk/",
  "status": "reviewing",
  "context_translation": "河岸",
  "source_sentence": "The bank of the river...",
  "ai_analysis": "在此语境中，bank 指...",
  "definitions": [
    { "pos": "noun", "definition": "...", "example": "..." }
  ]
}
```

词典数据来源：Free Dictionary API (`https://api.dictionaryapi.dev/api/v2/entries/en/{word}`)

---

### 4.3 NLP 服务（`nlp_service.py`）

```python
import spacy

nlp = spacy.load("en_core_web_sm")

def tokenize(raw_text: str) -> tuple[list[dict], list[dict]]:
    doc = nlp(raw_text)
    tokens = []
    sentences = []
    
    for sent_idx, sent in enumerate(doc.sents):
        sentences.append({"index": sent_idx, "text": sent.text})
        for token in sent:
            if not token.is_space:
                tokens.append({
                    "text": token.text,
                    "pos": token.tag_,          # 精细词性标注
                    "lemma": token.lemma_.lower(), # 词元（用于词库匹配）
                    "index": token.i,
                    "sentence_index": sent_idx,
                    "is_punct": token.is_punct,
                    "is_alpha": token.is_alpha,
                })
    
    return tokens, sentences
```

**关键设计：**
- 使用 `token.lemma_` 作为词库匹配键（"banks" → "bank"），保证跨文章正确匹配
- `is_punct`、`is_alpha` 供前端过滤不可点击的标点

---

### 4.4 跨文章同步（`annotation_service.py`）

```python
async def sync_to_other_articles(user_id: str, word: str, db: AsyncSession):
    """
    当 word 首次进入 vocabulary 时，为该用户所有包含该词的文章
    创建 gen_status='pending' 的 annotation 记录。
    已有记录的文章跳过（INSERT ... ON CONFLICT DO NOTHING）。
    """
    # 1. 查找该用户所有 tokens JSONB 中包含该词 lemma 的文章
    stmt = select(Article).where(
        Article.user_id == user_id,
        Article.tokens.contains([{"lemma": word}])  # GIN 索引加速
    )
    articles = await db.scalars(stmt)
    
    # 2. 批量插入 pending 记录
    for article in articles:
        await db.execute(
            insert(ArticleAnnotation)
            .values(article_id=article.id, user_id=user_id, word=word, gen_status="pending")
            .on_conflict_do_nothing()
        )
    await db.commit()
```

---

## 5. 前端设计

### 5.1 组件树

```
App
├── Router
│   ├── /articles            → ArticleListPage
│   │   └── ArticleCard
│   └── /articles/:id        → ArticleReaderPage
│       ├── ArticleHeader
│       ├── ArticleBody
│       │   └── WordToken[]         ← 核心组件
│       │       └── RubyAnnotation  ← 语境翻译注音
│       └── WordSidebar / WordDrawer (移动端)
│           ├── SidebarHeader       (音标 + TTS 按钮)
│           ├── ContextAnalysis     (AI 语境解析)
│           ├── DictionarySection   (常规释义 + 例句)
│           └── ReviewingActions    (仅 reviewing 状态显示)
│               ├── MasteredButton
│               └── ReviewAgainButton
```

### 5.2 状态管理（Zustand）

```typescript
// store/vocabStore.ts
interface VocabStore {
  // word → status 的映射，前端权威状态
  wordStatus: Record<string, WordStatus>;
  // word → annotation 的映射（包含翻译）
  annotations: Record<string, Record<string, Annotation>>; // articleId → word → annotation
  
  setWordStatus: (word: string, status: WordStatus) => void;
  setAnnotation: (articleId: string, word: string, annotation: Annotation) => void;
  initFromArticle: (articleId: string, data: ArticleResponse) => void;
}

// store/sidebarStore.ts
interface SidebarStore {
  isOpen: boolean;
  word: string | null;
  articleId: string | null;
  open: (word: string, articleId: string) => void;
  close: () => void;
}
```

### 5.3 `WordToken` 组件

```typescript
interface WordTokenProps {
  token: Token;       // { text, lemma, index, is_punct, is_alpha, sentence_index }
  articleId: string;
}

const WordToken: React.FC<WordTokenProps> = ({ token, articleId }) => {
  const { wordStatus, annotations } = useVocabStore();
  const { open: openSidebar } = useSidebarStore();
  const updateStatus = useMutation(/* PATCH /vocab/{word}/status */);
  const translateWord = useMutation(/* POST /translate-word */);

  if (token.is_punct || !token.is_alpha) {
    return <span>{token.text}</span>;
  }

  const lemma = token.lemma;
  const status = wordStatus[lemma] ?? "unseen";
  const annotation = annotations[articleId]?.[lemma];

  const handleClick = async () => {
    switch (status) {
      case "unseen":
      case "mastered":
        // 触发翻译，状态 → new
        await translateWord.mutateAsync({ word: lemma, sentence: getSentence(token), articleId });
        openSidebar(lemma, articleId);
        break;
      case "new":
        // 状态 → reviewing
        await updateStatus.mutateAsync({ word: lemma, status: "reviewing" });
        break;
      case "reviewing":
        // 状态不变，打开侧边栏
        openSidebar(lemma, articleId);
        break;
    }
  };

  return (
    <ruby
      className={cn(wordTokenStyles[status])}
      onClick={handleClick}
      data-word={lemma}
      data-status={status}
      aria-label={`${token.text}${annotation?.translation ? `, 翻译: ${annotation.translation}` : ""}`}
    >
      {token.text}
      {/* 仅 new 状态显示翻译注音 */}
      {status === "new" && annotation?.translation && (
        <rt className="text-xs text-red-600 font-normal">
          {annotation.translation}
          {annotation.is_fallback && <span className="text-gray-400">*</span>}
        </rt>
      )}
      {/* reviewing / mastered 无 rt，但通过样式区分 */}
      {(status === "reviewing" || status === "mastered") && <rt />}
    </ruby>
  );
};
```

### 5.4 单词状态样式映射

```typescript
// Tailwind 动态 class 须在 safelist 或通过 CSS 变量实现
const wordTokenStyles: Record<WordStatus, string> = {
  unseen:    "cursor-pointer hover:bg-gray-100",
  new:       "text-red-600 underline decoration-red-400 decoration-solid cursor-pointer",
  reviewing: "bg-yellow-100 border-b-2 border-yellow-400 cursor-pointer",
  // mastered: 灰色虚线下划线（非颜色区分，兼容色觉障碍）
  mastered:  "underline decoration-gray-300 decoration-dashed cursor-pointer",
};
```

> **可访问性说明：** `new` 用实线下划线，`reviewing` 用实色边框，`mastered` 用虚线下划线，确保在色觉障碍模式下（颜色失效）仍可区分，满足 PRD §4 可访问性要求。

### 5.5 侧边栏（`WordSidebar`）

- **PC：** 右侧固定面板，Framer Motion `x: "100%" → 0` 滑入动画
- **移动端：** 底部抽屉，`y: "100%" → 0`，支持手势 `drag="y"` 上滑展开/下滑收起
- **关闭触发：** 点击 `ArticleBody` 上的 `backdrop div`（`pointer-events-none` 非遮罩区域） 或键盘 `Escape`
- **reviewing 状态专属 UI：**
  ```
  ┌─────────────────────────────────┐
  │ [揭晓] 语境翻译: 河岸           │  ← 顶部醒目展示
  ├─────────────────────────────────┤
  │ /bæŋk/  🔊                      │
  │ AI 解析: ...                    │
  │ 词典释义: ...                   │
  ├─────────────────────────────────┤
  │ [已掌握]    [再复习一次]         │  ← 底部操作
  └─────────────────────────────────┘
  ```

---

## 6. AI 集成设计

### 6.1 翻译 Prompt（`ai_service.py`）

```python
TRANSLATION_SYSTEM_PROMPT = """
你是一个专业的英中词汇翻译助手。
任务：根据给定的英文句子，为指定单词提供最符合当前语境的中文翻译。
要求：
1. 翻译必须是当前句子语境下该词的确切含义
2. 翻译控制在 2-6 个中文字以内
3. 只返回 JSON，格式：{"translation": "翻译结果"}
"""

async def translate_in_context(word: str, sentence: str) -> str:
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": TRANSLATION_SYSTEM_PROMPT},
            {"role": "user", "content": f'单词: "{word}"\n句子: "{sentence}"'},
        ],
        response_format={"type": "json_object"},
        max_tokens=50,
        timeout=3.0,  # 严格 3 秒超时
    )
    result = json.loads(response.choices[0].message.content)
    return result["translation"]
```

### 6.2 语境解析 Prompt（侧边栏 AI Analysis）

```python
ANALYSIS_SYSTEM_PROMPT = """
你是一个英语词汇教学助手。
任务：为英语学习者解析单词在特定句子中的用法。
要求：
1. 用 1-3 句中文解析该词在此句中的含义和用法
2. 可以提及词根、常见搭配或同义词，帮助学习者理解和记忆
3. 语气友好，适合中文母语的英语学习者
4. 只返回 JSON，格式：{"analysis": "解析内容"}
"""
```

### 6.3 降级策略

```python
async def get_translation_with_fallback(word: str, sentence: str) -> tuple[str, bool]:
    """返回 (translation, is_fallback)"""
    try:
        translation = await asyncio.wait_for(
            translate_in_context(word, sentence), 
            timeout=3.0
        )
        return translation, False
    except (asyncio.TimeoutError, OpenAIError):
        # 降级：调用 Free Dictionary API 取第一个释义
        definition = await dict_service.get_first_definition(word)
        return f"{definition}（通用释义）", True
```

---

## 7. 关键业务流程

### 7.1 首次点击生词（unseen → new）

```
用户点击词 "bank"
    │
    ▼
WordToken.handleClick()
    │── 前端乐观更新：wordStatus["bank"] = "new"（即时变红）
    │
    ▼
POST /api/v1/translate-word
{word: "bank", sentence: "...", article_id: "..."}
    │
    ├─[< 3s] AI 返回 "河岸"
    │            │── 更新 article_annotations（当前文章）
    │            │── INSERT vocabulary(word="bank", status="new", ...)
    │            │── BackgroundTasks: sync_to_other_articles("bank")
    │            └── 返回 {translation:"河岸", is_fallback:false}
    │
    └─[超时] 词典降级
                 │── 返回 {translation:"河岸（通用释义）", is_fallback:true}
    │
    ▼
前端更新：
    │── annotations[articleId]["bank"] = {translation: "河岸", ...}
    │── 侧边栏打开（加载详情）
    └── ruby 注音渲染
```

### 7.2 文章加载（含历史标注恢复）

```
GET /api/v1/articles/{id}
    │
    ▼
后端查询 article_annotations（该文章所有已标注词）
    │
    ├─ gen_status="done"  → 直接返回 translation
    ├─ gen_status="pending" → 触发 BackgroundTasks 翻译，返回 translation=null
    └─ gen_status="failed"  → 返回 is_fallback=true，translation=词典释义
    │
    ▼
前端初始化 vocabStore（wordStatus + annotations）
    │
    ├─ pending 词：每 2s 轮询 GET .../annotations?words=...
    │  直到全部 done（最多轮询 10 次后停止，避免无限轮询）
    └─ 完成后更新 annotations，触发组件重渲染
```

### 7.3 状态切换完整流程

| 当前状态 | 点击行为 | 前端动作 | API 调用 | 后端动作 |
|----------|----------|----------|----------|----------|
| unseen | 点击词 | 乐观更新 → new | POST /translate-word | INSERT vocab + annotation |
| new | 点击词 | 乐观更新 → reviewing | PATCH /vocab/bank/status | status=reviewing, updated_at |
| reviewing | 点击词 | 打开侧边栏，状态不变 | GET /vocab/bank/detail | 仅读，无写 |
| reviewing | 侧边栏"已掌握" | 更新 → mastered | PATCH /vocab/bank/status | status=mastered, mastered_at |
| reviewing | 侧边栏"再复习"或关闭 | 无变化 | 无 | 无 |
| mastered | 点击词 | 乐观更新 → new | POST /translate-word（复用词条） | UPDATE vocab status=new, updated_at |

---

## 8. 性能与可靠性设计

### 8.1 文章渲染 ≤ 500ms

- 文章 tokens 存于 `articles.tokens`（JSONB），无需实时 NLP
- 初始化 vocabStore 时批量设置状态（O(n) 一次遍历）
- `WordToken` 使用 `React.memo`，避免无关重渲染
- 文章分段渲染：每段落独立为一个 `<p>` 组件，减少单次渲染树深度

### 8.2 侧边栏加载 ≤ 1s

- 侧边栏内容分两阶段加载：
  1. 立即展示：已有的 `context_translation`（来自 vocabStore，0ms）
  2. 异步加载：`GET /vocab/{word}/detail`（音标 + AI 解析 + 词典）

- AI 语境解析使用 `gpt-4o-mini`（更快），侧边栏只需 1-3 句话
- 词典 API 响应通常 < 200ms

### 8.3 乐观更新策略

所有状态切换均先更新前端状态（立即生效），再发请求。若请求失败（网络错误），React Query 自动 rollback 并 toast 提示用户。

### 8.4 AI 降级

- 超时 3s → 词典释义 + `is_fallback=true`
- 词典 API 失败 → 返回空字符串 + `is_fallback=true`，状态切换正常进行
- 两层降级均不阻塞 UI，满足 PRD §4 可用性要求

---

## 9. 可访问性实现

PRD 要求：红色/黄色状态须同时提供非颜色视觉区分。

| 状态 | 颜色 | 非颜色区分 | ARIA |
|------|------|------------|------|
| new | 红色 | 实线下划线（decoration-solid） | `aria-label="bank, 翻译: 河岸"` |
| reviewing | 黄色背景 | 底部实色边框 `border-b-2` | `aria-label="bank, 状态: 巩固中"` |
| mastered | 无特殊色 | 灰色虚线下划线（decoration-dashed） | `aria-label="bank, 状态: 已习得"` |
| unseen | 无 | 无（默认黑色） | 无额外 aria |

**高对比度媒体查询：**
```css
@media (forced-colors: active) {
  [data-status="new"]       { text-decoration: underline solid; }
  [data-status="reviewing"] { outline: 2px solid ButtonText; }
  [data-status="mastered"]  { text-decoration: underline dashed; }
}
```

---

## 10. 目录结构

```
english-learning/
├── prd.md
├── tdd.md                    ← 本文档
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── WordToken.tsx
│   │   │   ├── WordSidebar.tsx
│   │   │   ├── WordDrawer.tsx   (移动端)
│   │   │   ├── ArticleBody.tsx
│   │   │   └── RubyAnnotation.tsx
│   │   ├── store/
│   │   │   ├── vocabStore.ts
│   │   │   └── sidebarStore.ts
│   │   ├── hooks/
│   │   │   ├── useWordClick.ts
│   │   │   └── useAnnotationPolling.ts
│   │   ├── api/
│   │   │   └── client.ts       (ky 封装)
│   │   ├── pages/
│   │   │   ├── ArticleListPage.tsx
│   │   │   └── ArticleReaderPage.tsx
│   │   └── types/
│   │       └── index.ts
│   ├── package.json
│   └── vite.config.ts
└── backend/
    ├── app/
    │   ├── main.py
    │   ├── config.py
    │   ├── database.py
    │   ├── models/
    │   ├── schemas/
    │   ├── routers/
    │   ├── services/
    │   └── background/
    ├── alembic/
    ├── tests/
    └── requirements.txt
```

---

## 附录：开放设计决策

以下决策在 V1.0 实现中需确认：

1. **用户认证：** PRD 未提及认证，TDD 假设已有用户系统（JWT Token）。实际实现需补充 `/auth` 路由或接入第三方 OAuth。
2. **文章粘贴 vs 上传：** 前端同时支持文本框粘贴和文件上传（.txt），后端统一接收 `raw_text`。
3. **轮询 vs SSE：** V1.0 使用前端轮询（简单）；如 pending annotations 数量较多导致频繁轮询，Post-MVP 改为 SSE（`GET /api/v1/articles/{id}/annotations/stream`）。
4. **词元匹配精度：** 使用 spaCy lemma 匹配可能将 "better" 匹配到 "good"，对学习场景不准确。**决策：使用小写原形匹配（`token.lower_`）而非 lemma，vocabulary.word 存原形。** 跨文章同步时匹配小写 text 而非 lemma。
