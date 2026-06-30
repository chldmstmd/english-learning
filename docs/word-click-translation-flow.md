# Translation Request Flow

This document describes the current minimal translation path. The Web UI is a test shell; the durable product surface is the translation API that can be reused by the browser extension and future clients.

## Realtime Translation

Endpoint:

```text
POST /api/v1/translate-word
```

Input:

```json
{
  "word": "bank",
  "lemma": "bank",
  "sentence": "The boat reached the bank of the river.",
  "article_id": "...",
  "sentence_index": 0,
  "word_index": 5
}
```

Flow:

```text
validate article ownership
  -> upsert minimal user word state
  -> check paragraph_translations by article_paragraph_id's paragraph_version_id + sentence_index + word_index
  -> cache hit: return cached contextual translation
  -> cache miss: call AI single-word translation
  -> store position annotation
  -> return translation
```

The realtime path is latency-sensitive. It sends one target word plus its sentence context and expects a short JSON response:

```json
{"translation": "河岸"}
```

## Pretranslation

Endpoint:

```text
POST /api/v1/articles/{article_id}/translate
```

Flow:

```text
validate article ownership
  -> spawn background task
  -> mark article translation_status = processing
  -> collect alpha tokens from current paragraph_versions
  -> group words by paragraph and sentence
  -> split paragraph words into sentence-preserving chunks
  -> skip chunks already present in paragraph_translations
  -> call batch AI translation per missing chunk
  -> write paragraph_translations cache after each chunk
  -> update article translation progress after each chunk
  -> mark article translation_status = done
```

The current batch implementation sends the article text plus sentence-grouped word IDs in one request. The model returns a JSON object keyed by position IDs:

```json
{
  "0_5": "河岸",
  "1_2": "银行"
}
```

These results are cached by paragraph version and position, not by lemma, because the same word can have different meanings in different paragraph contexts.

## Provider Layer

The provider layer currently lives in `backend/app/services/ai_service.py`.

Default provider selection is `deepseek`, configured through:

```text
DEEPSEEK_API_KEY
DEEPSEEK_MODEL
DEEPSEEK_BASE_URL
```

Both realtime and pretranslation use the same provider adapter and JSON parsing style. Realtime uses a small prompt and short timeout; pretranslation uses sentence-preserving chunks, a larger prompt budget, and a longer timeout.

## Storage

`paragraph_translations` is the pretranslation cache:

```text
paragraph_version_id + sentence_index + word_index -> translation
```

`paragraph_annotations` records the result a user actually requested by clicking a word:

```text
article_id + user_id + article_paragraph_id + sentence_index + word_index -> translation
```

## Known Limits

- Pretranslation progress is tracked at cached-position granularity; a row with an empty translation still counts as processed.
- Background tasks run in the FastAPI process, not a durable queue.
- The Web UI still carries a minimal word-state layer for testing repeated clicks.
