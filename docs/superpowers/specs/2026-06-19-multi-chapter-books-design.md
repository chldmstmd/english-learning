# Multi-Chapter Books & Reading Progress Design

## Summary

引入「书」(Book) 这一容器概念,支持多章节长篇阅读,采用起点中文网式的两层结构:**书是容器,书里增量创建多个章节,每章是一个普通 article**。同时记录续读位置(读到第几章、章内第几句),让用户重新打开时能从上次中断处继续。

核心原则:**独立文章的体验完全不变,书是叠加在现有结构上的一层新组织方式,与独立文章共用同一个阅读器和同一套生词/翻译机制。**

## 心智模型

- **书 (Book)** = 章节的容器 + 进度追踪器。
- **章节 (Chapter)** = 长了「归属」(`book_id`) 和「上下章」(`chapter_order`) 的普通 article。
- **独立文章** = 不属于任何书的 article(`book_id` 为 null),即现状。

三者共用同一个阅读器、同一套 tokens/sentences/翻译缓存/生词标注机制。

## 数据模型

### 新增 `books` 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String(36) PK | uuid |
| user_id | String(36) | 创建者,index |
| title | Text | 书名 |
| cover_image_url | Text \| null | 可选封面 |
| source_category | String(64) \| null | 可选分类 |
| is_library | Boolean, default false | 是否公共书库(为未来管理员功能预留,与 `Article.is_library` 对齐) |
| created_at | DateTime | |

### `articles` 表新增字段

| 字段 | 类型 | 说明 |
|------|------|------|
| book_id | String(36) \| null | 外键 → books.id;null = 独立单篇(现状不变) |
| chapter_order | Integer \| null | 章节序号,决定阅读顺序;独立文章为 null |

> Article 的 tokens/sentences/翻译缓存/生词标注机制**一行都不用改**。一章就是一个普通 article,只是多了「属于某本书的第 N 章」这层归属。

### 扩展 `user_reading_history` 表

现有表只记 `last_read_at`(用于书库列表显示「已读」)。新增:

| 字段 | 类型 | 说明 |
|------|------|------|
| book_id | String(36) \| null | 读到哪本书(独立文章为 null) |
| last_sentence_index | Integer \| null | 章内读到第几句(续读锚点) |

「上次读到哪」= `article_id`(第几章)+ `last_sentence_index`(章内第几句)。书级别的「读到第几章」通过该 article 的 `chapter_order` 自然得到。

## 续读锚点与编辑漂移

锚点采用**句子 index**(`last_sentence_index`),复用文章已有的 `sentence_index`。文本不变时锚点稳定、可精确定位。

**编辑章节会导致 index 漂移**(在前面插入/删除句子会使旧 index 指向错误内容)。处理策略(参考网文站「大改即重置」惯例,选最简方案):

> **编辑章节后,若句子数 (`len(sentences)`) 发生变化,则把该章在 `reading_history` 的 `last_sentence_index` 重置为 0(从章首开始);句子数不变则保留。**

理由:真实网文站章节发布后多为「捉虫」式编辑(改错别字、标点,不增删句子),index 不漂;真要结构性大改,重置到章首符合用户预期(内容都变了,旧位置无意义)。一行判断即可实现。未来若出现频繁大改需求,再升级为新旧句子 diff 映射。

## API 端点

### 书相关(新增)

```
POST   /api/v1/books                      创建书 (title, 可选 cover/category) → 返回 book
GET    /api/v1/books                      列出我的书 (含章节数、阅读进度)
GET    /api/v1/books/{book_id}            书详情:元信息 + 章节目录 + 续读位置
POST   /api/v1/books/{book_id}/chapters   往书里加一章 (title, raw_text) → 复用现有分词/翻译/标注流程
DELETE /api/v1/books/{book_id}            删书 (级联删除其所有章节 article)
```

### 章节编辑(新增)

```
PUT    /api/v1/articles/{article_id}      编辑正文/标题 → 重新分词、重建 tokens/sentences、重刷翻译缓存
                                          若句子数变化 → 重置该章 last_sentence_index=0
```

### 续读位置(新增)

```
PUT    /api/v1/articles/{article_id}/progress   上报章内进度 {last_sentence_index}
                                                (同时更新 reading_history 的 book_id 指向)
```

### 列表页(沿用现有,前端合并)

前端同时调 `GET /books` 和 `GET /articles`,在列表页合并展示(实现简单,无需新增后端混合接口)。

### 章节顺序

`chapter_order` 在加章时自动取「当前书内最大值 + 1」。MVP 不做拖拽重排 (YAGNI)。

## 关键逻辑

1. **加章复用单篇创建**:`POST /books/{id}/chapters` 内部直接走现有 `create_article` 逻辑,额外塞入 `book_id` 与 `chapter_order`。分词、10000 词上限、翻译缓存、生词标注全部照旧。
2. **编辑重置进度**:`PUT /articles/{id}` 重新分词后比较新旧 `len(sentences)`,不相等则清零该 article 在 `reading_history` 的 `last_sentence_index`。
3. **「继续阅读」**:查 `reading_history` 中该 book 的记录 → 拿到 `article_id` + `last_sentence_index` → 前端打开该章并滚到对应句。

## 编辑权限

- 用户只能编辑/删除**自己创建**的书与文章。
- 公共文库(`is_library = true`,含 VOA)普通用户**只读**。

## UX 设计

### 1. 列表页(入口):书和独立文章并列

混合列表,两种卡片:
- **📖 书卡片** — 书名、封面、章节数、阅读进度(如「第 3/12 章」)。点击进入**书详情页**(非直接进阅读器)。
- **📄 独立文章卡片** — 与现状一致,点击直接进阅读器。

视觉上用图标/角标区分。VOA 书库保持不动。

### 2. 书详情页(新页面):章节目录

- 顶部:书名、封面、分类
- **「继续阅读」按钮** — 跳到上次读到的那一章那一句(续读主入口)
- **章节目录** — 按 `chapter_order` 列出每章:标题、字数、已读/未读、章内进度
- **「+ 添加章节」按钮** — 像连载更新,随时加新章;点开即现有的「写文章」表单(标题 + 正文),提交后走完整的分词/翻译/标注流程
- 点目录中某章 → 进阅读器读该章

### 3. 阅读器:基本不变,书章节多「上下章」导航

复用现有阅读器(一章 = 普通 article)。增量:
- 若 article 属于某书(`book_id` 非空):多出**「上一章 / 下一章」**导航与「第 N 章」标识
- 若是独立文章:无此导航,与现状完全一致
- 进入/滚动时记录与恢复 `last_sentence_index`(书与独立文章均生效)

### 4. 续读位置:两个层级

- **书级**:「读到第 3 章」→ 列表页进度、书详情页「继续阅读」
- **章内**:「第 3 章读到第 42 句」→ 重新打开自动滚到该句

### 5. 创建流程分叉

- **「写一篇文章」** — 现状,生成独立文章
- **「创建一本书」** — 只填书名(可选封面/分类),建空书 → 进书详情页 → 「+ 添加章节」逐章录入

## Post-MVP / 未来方向(本期不实现)

- **管理员公共文库管理界面**:管理员可上传、管理公共文库,包括公共的「书」。数据模型已为此预留 `Book.is_library` 字段(与 `Article.is_library` 对齐),将来加 admin 界面无需改表结构。
- **章节拖拽重排**。
- **编辑漂移的 diff 映射**(当前用「句子数变化即重置」)。
