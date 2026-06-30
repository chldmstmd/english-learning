# Translation Service Microservice Design

## Goal

Move the translation engine behind an internal HTTP microservice while keeping the existing reader, word-click translation, article pretranslation, database cache, and frontend APIs unchanged.

## Current State

The reusable translation code lives in `backend/app/translation_engine/` and has no database dependency. Backend callers access it through `backend/app/services/translation_engine_service.py`.

Current backend responsibilities:

- `backend/app/routers/translate.py` checks paragraph translation cache, calls the engine on cache miss, and writes annotations.
- `backend/app/services/batch_translation_service.py` builds paragraph-version chunks, calls the engine for each missing chunk, and writes `paragraph_translations`.
- `backend/app/services/settings_service.py` stores runtime settings such as `ai_provider` and `use_free_translation_fallback`.
- `backend/app/config.py` stores provider environment settings such as API keys, model names, and base URLs.

Docker currently only starts PostgreSQL through `docker-compose.yml`.

## Approved Service Boundary

Create an independent FastAPI service named `translation-service`.

The backend will call `translation-service` over HTTP. The backend remains responsible for auth, article ownership, paragraph cache lookup, annotation writes, pretranslation progress, retries, and database writes. The translation service is responsible only for provider calls, prompts, JSON parsing, fallback translation, and provider-specific request options.

This is an internal service boundary, not a public user-facing API. The frontend API remains unchanged.

## Endpoints

### `GET /health`

Returns:

```json
{"status": "ok"}
```

### `POST /v1/translate/context`

Translates one word or lemma in sentence context.

Request:

```json
{
  "word": "bank",
  "sentence": "The boat reached the bank of the river.",
  "source_language": "en",
  "target_language": "zh-CN",
  "ai_provider": "deepseek",
  "use_fallback": true
}
```

Response:

```json
{
  "translation": "河岸",
  "is_fallback": false
}
```

Behavior:

- `use_fallback: false` calls only the configured AI provider. Provider errors become HTTP 503.
- `use_fallback: true` calls the AI provider first. If it fails, the service tries the free fallback translator. Fallback success returns `is_fallback: true`.
- Unknown `ai_provider` values become HTTP 400.
- Provider responses that are not valid JSON or do not include a string `translation` become HTTP 502.

### `POST /v1/translate/batch`

Translates a sentence-preserving chunk of article tokens.

Request:

```json
{
  "article_text": "The bank approved five loans.",
  "word_entries": [[0, 1, "bank"], [0, 2, "approved"]],
  "sentences": [
    {"index": 0, "text": "The bank approved five loans."}
  ],
  "ai_provider": "deepseek"
}
```

Response:

```json
{
  "translations": {
    "0_1": "银行",
    "0_2": "批准"
  }
}
```

Behavior:

- Batch requests do not use fallback translation.
- Provider errors become HTTP 503.
- Invalid provider JSON becomes HTTP 502.
- The service preserves the existing key format, `sentence_index_word_index`.

## Runtime Settings Flow

The backend owns user/runtime settings. It maps current backend settings into translation service request fields:

- `settings_service.load()["ai_provider"]` -> `ai_provider`
- `settings_service.load()["use_free_translation_fallback"]` -> `use_fallback`

The translation service does not read backend `settings.json`.

Provider secrets and static provider configuration live in the translation service environment:

- `DEEPSEEK_API_KEY`
- `DEEPSEEK_MODEL`
- `DEEPSEEK_BASE_URL`
- `OPENAI_API_KEY`
- `GEMINI_API_KEY`

## Code Layout

Create:

- `translation-service/translation_service/main.py`: FastAPI app and endpoint wiring.
- `translation-service/translation_service/config.py`: service-local pydantic settings for provider env vars.
- `translation-service/translation_service/schemas.py`: request and response models.
- `translation-service/translation_service/engine_factory.py`: constructs `TranslationEngine` with service-local settings.
- `translation-service/requirements.txt`: minimal service dependencies.
- `translation-service/Dockerfile`: image for the translation service.
- `backend/Dockerfile`: image for the existing backend API.

Modify:

- `backend/app/config.py`: add `TRANSLATION_SERVICE_URL` with local default `http://127.0.0.1:8001`.
- `backend/app/services/translation_engine_service.py`: replace direct engine calls with an HTTP client that preserves the current Python API.
- `docker-compose.yml`: add `backend` and `translation-service` services and wire backend to `http://translation-service:8001`.

The existing `backend/app/translation_engine/` package remains the canonical engine implementation. The translation service imports it as top-level `translation_engine` by running with `backend/app` on `PYTHONPATH`. The microservice package is named `translation_service`, not `app`, so it does not shadow the backend `app` package or the standalone `translation_engine` package.

## Backend Compatibility

The following backend-facing functions keep their current signatures:

- `translate_in_context(...) -> str`
- `translate_in_context_with_fallback(...) -> TranslationResult`
- `batch_translate_article(...) -> dict[str, str]`

Existing callers in `translate.py`, `batch_translation_service.py`, and `ai_service.py` should not need semantic changes. HTTP failures are converted back into existing translation engine exceptions so routers keep returning the same user-facing status codes.

## Docker Compose

`docker-compose.yml` should run:

- `db`: existing PostgreSQL service.
- `translation-service`: internal FastAPI service on container port `8001`.
- `backend`: existing FastAPI API on container port `8000`, with `DATABASE_URL` pointing to `db` and `TRANSLATION_SERVICE_URL=http://translation-service:8001`.

Expose backend on host `8000`. Expose translation service on host `8001` for local debugging.

## Error Handling

The translation service returns structured error responses through FastAPI `HTTPException`.

Backend client mapping:

- HTTP 400 from service -> `TranslationProviderError`
- HTTP 502 from service -> `TranslationResponseError`
- HTTP 503 or connection failures -> `TranslationUnavailableError`
- HTTP timeout -> `TranslationUnavailableError`

Single-word router behavior remains unchanged: unavailable translation becomes HTTP 503 to the frontend.

## Testing

Add focused tests before implementation:

- Translation service endpoint test for `POST /v1/translate/context` with `use_fallback: false`.
- Translation service endpoint test for `POST /v1/translate/context` with `use_fallback: true` returning fallback.
- Translation service endpoint test for `POST /v1/translate/batch`.
- Backend client test that `translate_in_context_with_fallback()` sends `use_fallback: true` and maps `is_fallback`.
- Backend client test that `batch_translate_article()` sends existing word entry and sentence payload shape.
- Backend client test that a 503 response maps to `TranslationUnavailableError`.

Keep existing translation engine unit tests. They prove prompt/provider behavior independent of HTTP.

## Out of Scope

- Moving translation cache writes into the translation service.
- Giving the translation service database access.
- Changing frontend routes or response shapes.
- Adding service authentication between backend and translation service.
- Splitting the translation service into a separate repository.
- Replacing the current provider adapters.
