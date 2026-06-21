# 按位置翻译 + 单词表重构 设计文档

**日期**: 2026-06-21
**状态**: 待 review
**作者**: brainstorming session (Ensheng + Claude)

## 背景与目标

当前点击文中任意一个单词，会把**全文该词（按 lemma）的所有出现位置**一起染色并显示译文。这带来三个问题：

1. **一词多义无法区分** —— "bank"（河岸/银行）在不同句子里只能共用一条译文。
2. **"标红却没译文"的割裂** —— 译文显示被学习状态（颜色）绑死（`showTranslation = status==="new" && annotation`），重开文章时同词其它位置标红却无译文。
3. **token 浪费** —— 跨文章预翻译机制（`sync_word_to_user_articles_task` 等）会把一个生词在用户所有文章里都预先翻译。

### 用户的 mental model（决策依据）

- **mm1**：单词表是辅助，用户不应频繁去单词表 → 阅读视图是主战场。
- **mm2**：用户不会反复读同一篇文章；后续希望主动标出用户的生词 → 真正有长期价值的是"用户认识/不认识哪些词"（按词、跨文章）。
- **mm3**：保持翻译精准 → 必须带本句上下文，区分一词多义。
- **mm4**：不浪费 AI token → 只翻用户点的那一处；跨文章标生词时不预先翻译。

### 目标

- 点击一个词，只翻译/显示**被点击的那一处**（按 token 位置），按本句精准翻译。
- 点击处的译文**持久化**，重开文章仍在（不重复花 token）。
- 用户的生词在**所有文章**里被标出（按 lemma，跨文章，不预先翻译）。
- 单词表从"AI 上下文译文"改为"词典义 + 点击位置链接"。
- 原文编辑后，失效的位置标注有 fallback，不产生错位误导。

## 核心架构：双轨模型

把现在耦合在一起的"颜色 + 译文"拆成两条互不干扰的轨道。

### 轨道 A — 生词提示（按词 lemma，跨文章）

- **数据来源**：`vocabulary` 表（按 lemma）。**不改动。**
- **视觉**：凡属于用户生词本、且**未 mastered** 的词，正文里给单一高亮（如琥珀色下划线），表示"这是你当前未掌握的生词"。
- **不带译文**（省 token，mm4）。同一个词全文所有位置都有此提示——按词成立。
- **跨文章生效**：打开任意文章，命中生词本的词自动高亮（mm2）。
- **纯前端计算**：文章 tokens 的 lemma ∩ 用户生词本 lemma 集合（排除 mastered）。

### 轨道 B — 这一处的译文（按位置 token index，单篇内）

- **数据来源**：`article_annotations` 表（改造为按位置）。
- **视觉**：仅用户**在这一处点击查看过**的 token，上方显示红字译文。
- **带译文**，按**本句**精准翻译（mm3）。
- **持久化**：存库，重开文章该处译文仍在。
- 只作用于点击的那**一个** token，全文其它同词位置不受影响。

### 两轨叠加规则

```
某个 token 最终样式：
  ┌─ 在生词本且未 mastered? → 单一高亮（虚线下划线）
  └─ 这一处点击过?          → 上方红字译文（按本句翻译）
独立判断、可叠加：
  • 生词、此处没点 → 只有高亮（提示：这是生词，要看释义点一下）
  • 生词、此处点过 → 高亮 + 译文
  • 非生词、点过   → 译文（临时查词）
  • 已 mastered    → 无高亮（毕业，恢复普通词）
```

这把原来的"标红却没译文"从 bug 转为 feature：那是"生词提示但未展开释义"，看不看由用户点，点了才花 token、才按本句精准翻。

## 颜色模型（收敛）

去掉正文内三级颜色（new/reviewing/mastered），原因：译文与颜色解耦后，"红色无译文"与"黄色"在正文里无区别，三级失去意义。

- 正文里**只有一种高亮色** = "当前未掌握的生词"（new/reviewing 都用它；mastered 退出高亮）。
- 三级学习状态依然存在于数据、单词表、侧栏，**不再画进正文颜色**。
- 高亮 = `lemma ∈ 生词本 且 status ≠ mastered`。

### 点击交互（替代旧的 红→黄→侧栏 生命周期）

按位置两态：

```
点一个词：
  此处还没显示译文 → 显示本处译文（首次点：调 AI 按本句翻 + 该词入生词本）
  此处已显示译文   → 打开侧栏（词典义 / 出现位置链接 / 标记学习状态）
学习状态 reviewing / mastered 的切换 → 都在侧栏操作
```

正文负责"查看本处释义"，侧栏负责"管理这个词"（mm1）。

**不保留**：正文内"点黄色藏译文自测"玩法（自测移到侧栏/单词表）。

## 单词表重构

单词表每个词条展示（均为词典级、按 lemma 的通用信息，与 AI 上下文译文解耦）：

1. **中文词义**（`free_translation_service`，谷歌翻译，脱离上下文通用义）。
2. **英文释义 + 音标 + 例句**（`dict_service`，可展开）。
3. **点击位置链接**：用户点过该词的位置，最多保留**最近 3 处**，每条带文章标题 + 句子，可跳回原文那一处。

单词表不再依赖"某次点击时 AI 给的上下文译文" → 顺势省 token（mm4）。AI 上下文译文只活在正文（轨道 B）。

位置链接来源：改造后 `article_annotations` 按位置存了 `article_id + sentence_index + word_index + word(lemma) + source_sentence`，按 lemma 反查即得所有点击位置。

## 原文编辑 fallback

### 问题

轨道 B 译文按 `(article_id, sentence_index, word_index)` 存。文章编辑后重新 tokenize，位置全变 → 旧位置标注指向错误的词（"bank" 译文跑到 "river" 上方）。这是"错位"，比"丢失"更糟。

### 方案（方案 a：默默失效）

`edit_article` 重新 tokenize 后，对该文章所有位置标注做校验：

```
对每条旧标注，看新 tokens 里 (sentence_index, word_index) 处的 lemma：
  ├─ 仍是同一 lemma  → 位置有效，译文照常显示 ✅
  └─ lemma 不一致/越界 → 标记 is_stale=true，正文不再按此位置显示
```

校验同步在 `edit_article` 内完成（token 数通常数千内，一次比对很快），与现有的 `translation_status="stale"`、进度重置一起，不引入后台任务。

### 失效后兜底

- **正文**：失效处不再显示红字译文（避免错位误导）。但轨道 A 按 lemma，只要词还在生词本，依然有高亮——点一下按新句重新精准翻译（按需花 token，mm4）。
- **单词表**：失效位置链接降级（标"(原文已修改)"或跳文章开头）。译文文本仍在库，词典义不受影响。

**不做**：fallback b（自动在同句找同 lemma 新位置迁移）—— 一句多个同词会猜错。

## 改动面清单

### 数据模型

- **`article_annotations`**（approach B，按位置自带译文）：
  - 唯一键 `(article_id, user_id, word)` → `(article_id, user_id, sentence_index, word_index)`。
  - 列：`sentence_index`(新)、`word_index`(新)、`translation`、`source_sentence`、`is_fallback`、`is_stale`(新，编辑失效标记)、`word`(保留 lemma，用于单词表反查位置)、`gen_status`。
  - `create_all` 自动建表，无 Alembic 迁移（既有约定）。
- **`vocabulary`**：不动（按 lemma，单词表/复习真相源）。
- **`article_translations`**：不动，退回纯缓存角色（点击时命中省 token）。

### 后端

- `routers/translate.py` `/translate-word`：按位置 upsert 标注（已收到 `sentence_index`/`word_index` 参数，直接用）；**删除** `sync_word_to_user_articles_task` 调用。
- `services/annotation_service.py`：`upsert_annotation` 改按位置；`get_article_annotations` 返回结构 `{word: ...}` → `{"{sidx}-{widx}": ...}`；新增"按 lemma 反查点击位置（最近 3 处）"；**删除/弃用** `sync_word_to_user_articles_task`、`generate_pending_translations_task`（跨文章预翻译）。
- `routers/articles.py`：`create_article` 去掉给已知生词预埋 pending 标注；`edit_article` 加位置标注校验失效（fallback a）；`get_article` 返回 annotations 改按位置 key，去掉 pending 后台任务触发。
- `routers/vocab.py` / `schemas/vocab.py`：`VocabDetailResponse` 增加"点击位置链接（最近 3 处：article_id + 文章标题 + sentence_index + 句子）"。

### 前端

- `store/vocabStore.ts`：`articleAnnotations[articleId][lemma]` → `[tokenIndex]`；`wordStatuses` 保留（驱动高亮开关与单词表）。
- `components/WordToken.tsx`：查找键 lemma→`token.index`；`showTranslation` 改为"此处点过"（不再看 `status==="new"`）；高亮 = `lemma ∈ 生词本 且 ≠ mastered`；点击两态（显示译文 / 开侧栏）。
- 侧栏（`sidebarStore` + 侧栏组件）：承接学习状态管理（reviewing/mastered）+ 词典义 + 位置链接。
- 单词表页：中文义 + 英文释义（可展开）+ 最近 3 处位置链接（跳回原文）。

### 不做（YAGNI）

本地化 `target_lang` 旋钮、fallback b（自动位置迁移）、正文内三级颜色、正文内藏译文自测。

## 数据流（点击一个未查过的生词）

```
用户点击 token #i (lemma="bank", sidx, widx)
  → 前端：translateMutation
      onMutate: 乐观显示「此处」加载态（按 token.index）
  → POST /translate-word { word, lemma, sentence(本句), article_id, sentence_index, word_index }
  → 后端：
      1. vocab_service.upsert_word(lemma)  // 入生词本（轨道 A）
      2. 查 article_translations 缓存（命中省 token）
      3. 未命中 → ai_service.translate_in_context(lemma, 本句)  // mm3
      4. annotation_service.upsert_annotation(按位置: sidx, widx, translation, source_sentence)  // 轨道 B
      5. （不再 sync_word_to_user_articles_task）
  → 前端 onSuccess：
      setAnnotation(articleId, token.index, {translation, ...})  // 按位置
      该 lemma 入生词本 → 全文该词高亮（轨道 A，纯前端）
      仅 token #i 上方显示译文（轨道 B）
```

## 验收要点

- 点击 "bank" 的第 3 处：仅第 3 处显示译文；全文所有 "bank" 显示生词高亮；重开文章第 3 处译文仍在。
- 点同一词不同句：各自按本句翻译，互不覆盖。
- mastered 的词：正文无高亮。
- 编辑文章打乱位置：旧位置标注不在错误的词上显示译文；生词高亮仍在；重新点击按新句翻译。
- 单词表：展示中文义 + 可展开英文释义 + 最近 3 处位置链接；编辑失效的链接有降级提示。
- 不再发生一个生词被预翻译进所有文章的 token 浪费。
