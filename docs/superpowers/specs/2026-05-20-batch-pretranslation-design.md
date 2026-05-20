# Batch Pre-Translation Design

## Summary

文章入库时批量预翻译所有单词并缓存，用户点击单词时直接返回缓存结果，实现秒出体验。

## Trigger Timing

| 文章类型 | 触发时机 | 缓存共享 |
|---------|---------|---------|
| 公共库（VOA） | 入库时立即翻译 | 所有用户共享 |
| 用户上传 | 创建时立即翻译 | 仅该用户（绑定 article） |

## New Table: `article_translations`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | PK (Integer) | |
| article_id | FK → articles | |
| sentence_index | Integer | 第几句（0-based） |
| word_index | Integer | 句中第几个词（0-based） |
| word | String | 原词（原文形式） |
| lemma | String | 词元 |
| translation | String | 中文翻译 |

- 联合唯一约束：`(article_id, sentence_index, word_index)`
- 索引：`(article_id)` 用于整篇查询

## Article Status Field

在 `articles` 表新增字段 `translation_status`：

- `pending` — 文章已创建，翻译任务未开始
- `processing` — 正在翻译中
- `done` — 翻译完成
- `failed` — 翻译失败

## Batch Translation Flow

1. 文章入库（公共库收录 / 用户上传创建）
2. 设置 `translation_status = processing`
3. spaCy 对全文分句分词，得到 `[(sentence_index, word_index, word, lemma)]`
4. 将全文 + 词列表发给 Gemini 2.5 Flash（thinking 关闭），要求返回每个位置的中文翻译
5. 解析 AI 返回的 JSON，批量写入 `article_translations` 表
6. 设置 `translation_status = done`
7. 失败时设置 `translation_status = failed`

## Prompt Design

输入：整篇文章 + 每个词的位置信息
输出：JSON 数组，每项包含 `sentence_index`, `word_index`, `translation`

对于上下文，使用整篇文章作为 context，让模型对每个词位置给出语境翻译。

## translate-word Endpoint Change

现有 `POST /translate-word` 改动：

```
收到请求(article_id, word, lemma, sentence)
  → 查 article_translations(article_id, sentence_index, word_index)
  → 命中：直接返回 translation, is_fallback=false
  → 未命中：走现有逻辑（Gemini 实时翻译 → Google Translate fallback）
```

未命中是保底路径，正常情况下文章打开时预翻译已完成。

## Cost Estimate

- Gemini 2.5 Flash: input $0.15/1M tokens, output $0.60/1M tokens
- 一篇 600 词文章：input ~1,000 tokens, output ~9,000 tokens
- 单篇成本：≈ $0.006
- 1,000 篇文章：≈ $6

## Chunking Strategy

当前不设阈值，整篇一次请求。VOA 文章通常 500-800 词，Gemini 2.5 Flash 可处理（max output 65K tokens）。未来若支持长文（2000+ 词），按段落分段请求。

## Frontend Impact

- 前端根据 `translation_status` 显示状态提示（如 processing 时显示"正在准备翻译..."）
- 点击单词的交互逻辑不变，只是响应更快（缓存命中时无网络延迟感知）
