# Translate Engine Spec

本文档定义当前 `translate engine` 的职责边界、公开接口、输入输出契约和错误语义。它描述的是现有实现，而不是未来重构目标。

## 1. 目标

`translate engine` 是后端内部的语境翻译能力层，负责把调用方提供的英文词汇、句子和文章片段转换为短中文翻译。

核心目标：

- 为单词提供基于当前句子的 2-6 个中文字中文翻译。
- 为文章预翻译提供按文本位置标识的批量翻译结果。
- 隔离不同 AI provider 的调用细节。
- 在单词实时翻译失败时支持免费翻译 fallback。
- 对 provider 返回内容做最小 JSON 校验和规范化。

## 2. 非目标

`translate engine` 不负责以下事情：

- 不接收、不保存、也不理解 `article_id`。
- 不负责鉴权、用户权限或 HTTP 状态码。
- 不负责文章创建、删除、读取。
- 不负责 NLP 分词、词形还原、句子切分。
- 不负责选择哪些 token 需要翻译。
- 不负责文章切块、翻译进度、后台任务生命周期。
- 不负责数据库读写、缓存命中判断或 annotation 写入。
- 不负责前端展示状态。

这些能力分别由 router、NLP service、batch translation service、annotation service 和前端负责。

## 3. 模块边界

主要文件：

```text
backend/app/translation_engine/
  __init__.py
  engine.py
  providers.py
  prompts.py

backend/app/services/translation_engine_service.py
```

职责划分：

| 模块 | 职责 |
|------|------|
| `engine.py` | 选择 provider、构造 prompt、调用 provider、解析 JSON、fallback 编排 |
| `providers.py` | DeepSeek/OpenAI/Gemini/Google fallback 等外部服务适配 |
| `prompts.py` | 单词翻译 prompt、批量翻译 prompt、批量词表渲染 |
| `translation_engine_service.py` | 创建默认 singleton engine，并注入 settings 和 provider |

## 4. Provider 选择

运行时通过 `settings_service.load()` 读取 `ai_provider`：

```text
deepseek -> OpenAICompatibleProvider
openai   -> OpenAICompatibleProvider
gemini   -> GeminiProvider
google   -> gemini
```

默认 provider 是 `deepseek`。

未知 provider 必须抛出 `TranslationProviderError`。

## 5. Provider 接口

所有 AI provider 必须实现：

```python
async def complete_json(
    prompt: str,
    *,
    max_tokens: int,
    temperature: float,
    timeout: float,
    request_kind: Literal["single", "batch"],
) -> str:
    ...
```

契约：

- 返回值必须是 JSON 字符串。
- provider 不负责解析 JSON。
- provider 不负责 fallback。
- `request_kind` 用于区分单词翻译和批量翻译；Gemini 当前用它选择不同模型。
- 默认 DeepSeek provider 在 `request_kind="single"` 时会额外发送 `extra_body={"thinking": {"type": "disabled"}}`，避免实时单词翻译产生 reasoning tokens；批量翻译和其他 provider 不发送该参数。

## 6. 单词语境翻译

公开方法：

```python
async def translate_in_context(
    word: str,
    sentence: str,
    source_language: str = "en",
    target_language: str = "zh-CN",
) -> str
```

输入：

| 字段 | 说明 |
|------|------|
| `word` | 目标词；英文文章通常传 lemma |
| `sentence` | 目标词所在句子 |
| `source_language` | 原语言，默认 `en` |
| `target_language` | 目标语言，默认 `zh-CN` |

行为：

1. 使用 `TRANSLATION_PROMPT` 构造 prompt，prompt 内包含 `source_language` 和 `target_language`。
2. 调用当前 provider 的 `complete_json()`。
3. 请求参数固定为：

```text
max_tokens=100
temperature=0
timeout=5.0
request_kind="single"
```

默认 DeepSeek provider 会基于 `request_kind="single"` 关闭 thinking mode。该选项属于 provider 适配层行为，不改变 translate engine 的公开方法签名。

4. 解析 provider 返回 JSON。
5. 读取 `translation` 字段。
6. 如果 `translation` 不是字符串，抛出 `TranslationResponseError`。

期望 provider 返回：

```json
{"translation": "河岸"}
```

返回：

```python
"河岸"
```

## 7. 单词 fallback 翻译

公开方法：

```python
async def translate_in_context_with_fallback(
    word: str,
    sentence: str,
    source_language: str = "en",
    target_language: str = "zh-CN",
) -> TranslationResult
```

返回类型：

```python
@dataclass(frozen=True)
class TranslationResult:
    translation: str
    is_fallback: bool = False
```

行为：

1. 优先调用 `translate_in_context()`。
2. 成功时返回 `TranslationResult(translation=..., is_fallback=False)`。
3. AI provider 或 JSON 解析失败时，检查 runtime setting `use_free_translation_fallback`。
4. 如果 fallback 未开启，或未配置 fallback translator，抛出 `TranslationUnavailableError("AI translation unavailable")`。
5. 如果 fallback 开启，调用 `fallback_translator.translate(word, source_language=..., target_language=...)`。
6. fallback 成功时返回 `TranslationResult(translation=..., is_fallback=True)`。
7. fallback 也失败时，抛出 `TranslationUnavailableError("All translation services unavailable")`。

当前 fallback provider：

```text
GoogleFallbackTranslator
```

注意：fallback 只用于单词实时翻译，不用于批量文章预翻译。

## 8. 批量文章翻译

公开方法：

```python
async def batch_translate_article(
    article_text: str,
    word_entries: Sequence[tuple[int, int, str]],
    sentences: Sequence[dict],
) -> dict[str, str]
```

输入：

| 字段 | 说明 |
|------|------|
| `article_text` | 当前 chunk 的文章文本，供整体理解 |
| `word_entries` | 待翻译词列表，格式为 `(sentence_index, word_index, text)` |
| `sentences` | 句子列表，每项至少包含 `index` 和 `text` |

`article_id` 不是 translate engine 的输入。批量接口只关心文本内容、句子位置和词位置；文章身份、缓存归属和数据库写入由调用方处理。

行为：

1. 使用 `build_sentence_blocks()` 把词按句子渲染成 prompt 片段。
2. 使用 `BATCH_TRANSLATION_PROMPT` 构造 prompt。
3. 调用当前 provider 的 `complete_json()`。
4. 请求参数固定为：

```text
max_tokens=16000
temperature=0.1
timeout=180.0
request_kind="batch"
```

5. 解析 provider 返回 JSON object。
6. 将返回 object 的 key 和 value 都转换成字符串。

期望 provider 返回：

```json
{
  "0_5": "河岸",
  "1_2": "银行"
}
```

返回：

```python
{
    "0_5": "河岸",
    "1_2": "银行",
}
```

### 批量 key 契约

批量翻译的 key 必须是：

```text
{sentence_index}_{word_index}
```

示例：

```text
句子 0 的第 5 个词 -> "0_5"
```

调用方会用同样的 key 写回 `article_translations`。如果 prompt 中暴露的 key 和调用方读取的 key 不一致，缓存会写入空翻译。

## 9. Prompt 契约

单词 prompt 要求：

- AI 扮演英文阅读器的逐词 ruby 标注助手。
- 根据句子语境翻译指定目标单词。
- 只翻译目标单词本身，不翻译包含它的相邻短语、专名或搭配。
- 如果目标单词属于多词短语，只返回该单词在短语中的局部含义；例如 `University Press` 中 `University -> 大学`、`Press -> 出版社`。
- 中文翻译控制在 1-6 个中文字。
- 只返回 JSON。

批量 prompt 要求：

- 输入文章全文和按句子分组的待翻译词汇。
- 每个待翻译词的 ID 形如 `"0_1"`。
- 每个 ID 只翻译对应单词本身，不翻译相邻短语、专名或搭配。
- 多词短语按 token 拆分为局部含义；例如 `University Press` 中 `University -> 大学`、`Press -> 出版社`。
- 对虚词返回空字符串 `""`。
- 每个词汇 ID 都必须出现在返回 JSON 中。
- 只返回 JSON object。

## 10. 错误类型

| 错误 | 触发条件 |
|------|----------|
| `TranslationEngineError` | translate engine 基类错误 |
| `TranslationProviderError` | 未知 provider |
| `TranslationResponseError` | provider 返回非法 JSON 或缺少期望字段 |
| `TranslationUnavailableError` | AI 和可用 fallback 都无法完成翻译 |

provider 自身抛出的异常会被单词 fallback 路径捕获；批量翻译路径不捕获并转换这些异常，由上层 batch service 标记文章翻译失败。

## 11. 与调用方的集成

本节描述调用方如何使用 translate engine。这里出现的 `article_id` 只属于 router/service/database 层，不属于 translate engine 的接口契约。

### 实时查词

入口：

```text
POST /api/v1/translate-word
```

调用方职责：

- 校验文章属于当前用户。
- 优先查询 `article_translations` 位置级缓存。
- 缓存未命中时调用 `translate_in_context_with_fallback()`。
- 将结果写入 annotation。
- 返回 `translation` 和 `is_fallback`。

### 文章预翻译

入口：

```text
POST /api/v1/articles/{article_id}/translate
```

调用方职责：

- 创建后台任务。
- 将文章状态改为 `processing`。
- 从 tokens 中筛选 `is_alpha` 的词。
- 按句子保持边界切 chunk。
- 跳过已存在的 position cache。
- 对每个缺失 chunk 调用 `batch_translate_article()`。
- 将结果写入 `article_translations`。
- 更新进度字段。
- 全部完成后标记 `done`，失败时标记 `failed`。

## 12. 配置

默认 engine 通过 `translation_engine_service.py` 创建。

当前配置来源：

| 配置 | 用途 |
|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API key |
| `DEEPSEEK_MODEL` | DeepSeek 模型名 |
| `DEEPSEEK_BASE_URL` | DeepSeek OpenAI-compatible base URL |
| `OPENAI_API_KEY` | OpenAI API key |
| `GEMINI_API_KEY` | Gemini API key |
| `ai_provider` | runtime provider 选择 |
| `use_free_translation_fallback` | 是否启用单词 fallback |

## 13. 测试要求

translate engine 至少需要覆盖：

- 单词语境翻译返回 provider 的 `translation`。
- 单词翻译使用 `request_kind="single"`。
- provider 失败且 fallback 开启时返回 `is_fallback=True`。
- fallback 关闭时抛出 `TranslationUnavailableError`。
- 批量翻译使用 `request_kind="batch"`。
- 批量翻译将 provider 返回值规范化为 `dict[str, str]`。
- 批量 prompt 暴露的 key 必须是 `{sentence_index}_{word_index}`。
- `translation_engine` package 可以作为独立 package import。

## 14. 当前限制

- 批量翻译没有 fallback。
- 批量翻译不校验 provider 是否返回了所有请求的 key。
- 批量翻译会把非字符串 value 强制转换为字符串。
- 单词 fallback 只按 word 翻译，不携带 sentence context。
- Provider client 会缓存实例；如果 API key 或 base URL 在进程内变更，旧 client 可能继续使用旧配置。
- prompt、timeout、token budget 当前是硬编码。
