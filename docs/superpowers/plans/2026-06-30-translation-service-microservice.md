# Translation Service Microservice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the translation engine behind an internal FastAPI microservice and have the backend call it over HTTP while preserving existing backend APIs.

**Architecture:** Keep `backend/app/translation_engine/` as the single source of truth for prompt and provider behavior. Add a new `translation-service` FastAPI app that imports that engine as top-level `translation_engine`, and replace backend direct engine calls with an `httpx` client that preserves the existing `translation_engine_service.py` function signatures.

**Tech Stack:** Python, FastAPI, Pydantic Settings, httpx, pytest, Docker, docker compose.

---

## File Structure

- Create `translation-service/translation_service/__init__.py`: marks the microservice app package.
- Create `translation-service/translation_service/config.py`: provider env var settings local to the translation service.
- Create `translation-service/translation_service/schemas.py`: request and response models for `/v1/translate/context` and `/v1/translate/batch`.
- Create `translation-service/translation_service/engine_factory.py`: builds `TranslationEngine` using service env settings and per-request runtime settings.
- Create `translation-service/translation_service/main.py`: FastAPI app, `/health`, `/v1/translate/context`, and `/v1/translate/batch`.
- Create `translation-service/tests/test_translation_service.py`: endpoint tests with fake providers and fallback.
- Create `translation-service/requirements.txt`: minimal service dependencies.
- Create `translation-service/Dockerfile`: Docker image for the microservice.
- Modify `backend/app/config.py`: add `translation_service_url`.
- Modify `backend/app/services/translation_engine_service.py`: replace singleton in-process engine with HTTP client functions.
- Create `backend/tests/test_translation_engine_client.py`: backend HTTP client tests with `httpx.MockTransport`.
- Create `backend/Dockerfile`: Docker image for the backend API.
- Modify `docker-compose.yml`: run `db`, `translation-service`, and `backend`.

---

### Task 1: Translation Service Endpoint Tests

**Files:**
- Create: `translation-service/tests/test_translation_service.py`
- Create: `translation-service/translation_service/__init__.py`

- [ ] **Step 1: Write the failing tests**

Create `translation-service/translation_service/__init__.py` as an empty file.

Create `translation-service/tests/test_translation_service.py`:

```python
from __future__ import annotations

from fastapi.testclient import TestClient

from translation_engine.engine import TranslationEngine
from translation_service import main as service_main


class FakeProvider:
    def __init__(self, response: str = "", error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict] = []

    async def complete_json(self, prompt: str, **kwargs) -> str:
        self.calls.append({"prompt": prompt, **kwargs})
        if self.error:
            raise self.error
        return self.response


class FakeFallback:
    def __init__(self, translation: str) -> None:
        self.translation = translation
        self.calls: list[dict] = []

    async def translate(
        self,
        word: str,
        source_language: str = "en",
        target_language: str = "zh-CN",
    ) -> str:
        self.calls.append(
            {
                "word": word,
                "source_language": source_language,
                "target_language": target_language,
            }
        )
        return self.translation


def _override_engine(monkeypatch, engine: TranslationEngine) -> None:
    monkeypatch.setattr(service_main, "create_translation_engine", lambda runtime_settings: engine)


def test_context_translation_without_fallback_calls_provider_only(monkeypatch):
    provider = FakeProvider('{"translation": "银行"}')
    engine = TranslationEngine(
        providers={"deepseek": provider},
        fallback_translator=FakeFallback("fallback"),
        runtime_settings_loader=lambda: {},
    )
    _override_engine(monkeypatch, engine)
    client = TestClient(service_main.app)

    response = client.post(
        "/v1/translate/context",
        json={
            "word": "bank",
            "sentence": "The bank approved the loan.",
            "source_language": "en",
            "target_language": "zh-CN",
            "ai_provider": "deepseek",
            "use_fallback": False,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"translation": "银行", "is_fallback": False}
    assert provider.calls[0]["request_kind"] == "single"


def test_context_translation_with_fallback_returns_fallback_result(monkeypatch):
    provider = FakeProvider(error=RuntimeError("provider down"))
    fallback = FakeFallback("河岸")
    engine = TranslationEngine(
        providers={"deepseek": provider},
        fallback_translator=fallback,
        runtime_settings_loader=lambda: {},
    )
    _override_engine(monkeypatch, engine)
    client = TestClient(service_main.app)

    response = client.post(
        "/v1/translate/context",
        json={
            "word": "bank",
            "sentence": "The boat reached the bank.",
            "ai_provider": "deepseek",
            "use_fallback": True,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"translation": "河岸", "is_fallback": True}
    assert fallback.calls == [
        {
            "word": "bank",
            "source_language": "en",
            "target_language": "zh-CN",
        }
    ]


def test_batch_translation_returns_translation_map(monkeypatch):
    provider = FakeProvider('{"0_1": "银行", "0_2": "批准"}')
    engine = TranslationEngine(
        providers={"deepseek": provider},
        runtime_settings_loader=lambda: {},
    )
    _override_engine(monkeypatch, engine)
    client = TestClient(service_main.app)

    response = client.post(
        "/v1/translate/batch",
        json={
            "article_text": "The bank approved the loan.",
            "word_entries": [[0, 1, "bank"], [0, 2, "approved"]],
            "sentences": [{"index": 0, "text": "The bank approved the loan."}],
            "ai_provider": "deepseek",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"translations": {"0_1": "银行", "0_2": "批准"}}
    assert provider.calls[0]["request_kind"] == "batch"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd backend && PYTHONPATH=../translation-service:app .venv/bin/python -m pytest ../translation-service/tests/test_translation_service.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'translation_service'` or missing `translation_service.main`.

- [ ] **Step 3: Commit the failing tests**

Run:

```bash
git add translation-service/translation_service/__init__.py translation-service/tests/test_translation_service.py
git commit -m "test: define translation service endpoints"
```

---

### Task 2: Translation Service Implementation

**Files:**
- Create: `translation-service/translation_service/config.py`
- Create: `translation-service/translation_service/schemas.py`
- Create: `translation-service/translation_service/engine_factory.py`
- Create: `translation-service/translation_service/main.py`
- Test: `translation-service/tests/test_translation_service.py`

- [ ] **Step 1: Implement service settings**

Create `translation-service/translation_service/config.py`:

```python
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    gemini_api_key: str = Field("", alias="GEMINI_API_KEY")
    openai_api_key: str = Field("", alias="OPENAI_API_KEY")
    deepseek_api_key: str = Field(
        "",
        validation_alias=AliasChoices("DEEPSEEK_API_KEY", "deepseek_api_key"),
    )
    deepseek_model: str = Field(
        "deepseek-v4-flash",
        validation_alias=AliasChoices("DEEPSEEK_MODEL", "deepseek_model"),
    )
    deepseek_base_url: str = Field(
        "https://api.deepseek.com",
        validation_alias=AliasChoices("DEEPSEEK_BASE_URL", "deepseek_base_url"),
    )

    model_config = {
        "env_file": (".env", "translation-service/.env"),
        "populate_by_name": True,
        "extra": "ignore",
    }


settings = Settings()
```

- [ ] **Step 2: Implement schemas**

Create `translation-service/translation_service/schemas.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, Field


class ContextTranslationRequest(BaseModel):
    word: str
    sentence: str
    source_language: str = "en"
    target_language: str = "zh-CN"
    ai_provider: str = "deepseek"
    use_fallback: bool = True


class ContextTranslationResponse(BaseModel):
    translation: str
    is_fallback: bool = False


class SentenceBlock(BaseModel):
    index: int
    text: str


class BatchTranslationRequest(BaseModel):
    article_text: str
    word_entries: list[tuple[int, int, str]] = Field(default_factory=list)
    sentences: list[SentenceBlock] = Field(default_factory=list)
    ai_provider: str = "deepseek"


class BatchTranslationResponse(BaseModel):
    translations: dict[str, str]
```

- [ ] **Step 3: Implement engine factory**

Create `translation-service/translation_service/engine_factory.py`:

```python
from __future__ import annotations

from collections.abc import Mapping

from translation_engine import (
    GeminiProvider,
    GoogleFallbackTranslator,
    OpenAICompatibleProvider,
    TranslationEngine,
)

from .config import settings


def create_translation_engine(runtime_settings: Mapping[str, object]) -> TranslationEngine:
    return TranslationEngine(
        providers={
            "deepseek": OpenAICompatibleProvider(
                api_key_getter=lambda: settings.deepseek_api_key,
                model_getter=lambda: settings.deepseek_model,
                base_url_getter=lambda: settings.deepseek_base_url,
                single_request_extra_body={"thinking": {"type": "disabled"}},
            ),
            "openai": OpenAICompatibleProvider(
                api_key_getter=lambda: settings.openai_api_key,
                model_getter=lambda: "gpt-4o",
            ),
            "gemini": GeminiProvider(api_key_getter=lambda: settings.gemini_api_key),
        },
        fallback_translator=GoogleFallbackTranslator(),
        runtime_settings_loader=lambda: runtime_settings,
    )
```

- [ ] **Step 4: Implement FastAPI endpoints**

Create `translation-service/translation_service/main.py`:

```python
from __future__ import annotations

from fastapi import FastAPI, HTTPException

from translation_engine import (
    TranslationEngine,
    TranslationProviderError,
    TranslationResponseError,
    TranslationUnavailableError,
)

from .engine_factory import create_translation_engine
from .schemas import (
    BatchTranslationRequest,
    BatchTranslationResponse,
    ContextTranslationRequest,
    ContextTranslationResponse,
)

app = FastAPI(title="Translation Service")


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, TranslationProviderError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, TranslationResponseError):
        return HTTPException(status_code=502, detail=str(exc))
    if isinstance(exc, TranslationUnavailableError):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=503, detail="Translation provider unavailable")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/translate/context", response_model=ContextTranslationResponse)
async def translate_context(
    body: ContextTranslationRequest,
) -> ContextTranslationResponse:
    runtime_settings = {
        "ai_provider": body.ai_provider,
        "use_free_translation_fallback": body.use_fallback,
    }
    engine = create_translation_engine(runtime_settings)
    try:
        if body.use_fallback:
            result = await engine.translate_in_context_with_fallback(
                body.word,
                body.sentence,
                source_language=body.source_language,
                target_language=body.target_language,
            )
            return ContextTranslationResponse(
                translation=result.translation,
                is_fallback=result.is_fallback,
            )
        translation = await engine.translate_in_context(
            body.word,
            body.sentence,
            source_language=body.source_language,
            target_language=body.target_language,
        )
        return ContextTranslationResponse(translation=translation, is_fallback=False)
    except Exception as exc:
        raise _map_error(exc) from exc


@app.post("/v1/translate/batch", response_model=BatchTranslationResponse)
async def translate_batch(
    body: BatchTranslationRequest,
) -> BatchTranslationResponse:
    runtime_settings = {"ai_provider": body.ai_provider}
    engine = create_translation_engine(runtime_settings)
    try:
        translations = await engine.batch_translate_article(
            body.article_text,
            body.word_entries,
            [sentence.model_dump() for sentence in body.sentences],
        )
    except Exception as exc:
        raise _map_error(exc) from exc
    return BatchTranslationResponse(translations=translations)
```

- [ ] **Step 5: Run translation service tests to verify green**

Run:

```bash
cd backend && PYTHONPATH=../translation-service:app .venv/bin/python -m pytest ../translation-service/tests/test_translation_service.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit translation service implementation**

Run:

```bash
git add translation-service/translation_service
git commit -m "feat: add translation service api"
```

---

### Task 3: Backend Translation HTTP Client Tests

**Files:**
- Create: `backend/tests/test_translation_engine_client.py`

- [ ] **Step 1: Write the failing backend client tests**

Create `backend/tests/test_translation_engine_client.py`:

```python
from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.services import translation_engine_service
from app.translation_engine import TranslationUnavailableError


def _run(coro):
    return asyncio.run(coro)


def test_translate_with_fallback_posts_context_request(monkeypatch):
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content.decode()))
        return httpx.Response(200, json={"translation": "河岸", "is_fallback": True})

    monkeypatch.setattr(
        translation_engine_service.settings_service,
        "load",
        lambda: {"ai_provider": "deepseek", "use_free_translation_fallback": True},
    )
    monkeypatch.setattr(
        translation_engine_service,
        "_transport",
        httpx.MockTransport(handler),
    )

    result = _run(
        translation_engine_service.translate_in_context_with_fallback(
            "bank",
            "The boat reached the bank.",
        )
    )

    assert result.translation == "河岸"
    assert result.is_fallback is True
    assert calls == [
        {
            "word": "bank",
            "sentence": "The boat reached the bank.",
            "source_language": "en",
            "target_language": "zh-CN",
            "ai_provider": "deepseek",
            "use_fallback": True,
        }
    ]


def test_batch_translate_article_posts_batch_request(monkeypatch):
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content.decode()))
        return httpx.Response(200, json={"translations": {"0_1": "银行"}})

    monkeypatch.setattr(
        translation_engine_service.settings_service,
        "load",
        lambda: {"ai_provider": "openai", "use_free_translation_fallback": False},
    )
    monkeypatch.setattr(
        translation_engine_service,
        "_transport",
        httpx.MockTransport(handler),
    )

    result = _run(
        translation_engine_service.batch_translate_article(
            "The bank approved the loan.",
            [(0, 1, "bank")],
            [{"index": 0, "text": "The bank approved the loan."}],
        )
    )

    assert result == {"0_1": "银行"}
    assert calls == [
        {
            "article_text": "The bank approved the loan.",
            "word_entries": [[0, 1, "bank"]],
            "sentences": [{"index": 0, "text": "The bank approved the loan."}],
            "ai_provider": "openai",
        }
    ]


def test_service_503_maps_to_translation_unavailable(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "provider down"})

    monkeypatch.setattr(
        translation_engine_service,
        "_transport",
        httpx.MockTransport(handler),
    )

    with pytest.raises(TranslationUnavailableError, match="provider down"):
        _run(translation_engine_service.translate_in_context("bank", "by the bank"))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/test_translation_engine_client.py -q
```

Expected: FAIL because `translation_engine_service` does not expose `_transport` and still calls the in-process engine.

- [ ] **Step 3: Commit the failing tests**

Run:

```bash
git add backend/tests/test_translation_engine_client.py
git commit -m "test: define backend translation service client"
```

---

### Task 4: Backend Translation HTTP Client Implementation

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/services/translation_engine_service.py`
- Test: `backend/tests/test_translation_engine_client.py`

- [ ] **Step 1: Add backend service URL setting**

In `backend/app/config.py`, add this field to `Settings`:

```python
    translation_service_url: str = Field(
        "http://127.0.0.1:8001",
        alias="TRANSLATION_SERVICE_URL",
    )
```

- [ ] **Step 2: Replace backend direct engine access with HTTP client**

Replace `backend/app/services/translation_engine_service.py` with:

```python
from __future__ import annotations

from typing import Sequence

import httpx

from app.config import settings
from app.services import settings_service
from app.translation_engine import (
    TranslationProviderError,
    TranslationResponseError,
    TranslationResult,
    TranslationUnavailableError,
)

_transport: httpx.AsyncBaseTransport | None = None


def _runtime_settings() -> dict:
    return settings_service.load()


def _service_url() -> str:
    return settings.translation_service_url.rstrip("/")


async def _post(path: str, payload: dict, timeout: float) -> dict:
    try:
        async with httpx.AsyncClient(
            base_url=_service_url(),
            timeout=timeout,
            transport=_transport,
        ) as client:
            response = await client.post(path, json=payload)
    except httpx.TimeoutException as exc:
        raise TranslationUnavailableError("Translation service timed out") from exc
    except httpx.HTTPError as exc:
        raise TranslationUnavailableError("Translation service unavailable") from exc

    if response.status_code == 400:
        raise TranslationProviderError(_detail(response))
    if response.status_code == 502:
        raise TranslationResponseError(_detail(response))
    if response.status_code == 503:
        raise TranslationUnavailableError(_detail(response))
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise TranslationUnavailableError(_detail(response)) from exc
    return response.json()


def _detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text or "Translation service error"
    detail = body.get("detail") if isinstance(body, dict) else None
    return str(detail or "Translation service error")


async def translate_in_context(
    word: str,
    sentence: str,
    source_language: str = "en",
    target_language: str = "zh-CN",
) -> str:
    runtime_settings = _runtime_settings()
    payload = {
        "word": word,
        "sentence": sentence,
        "source_language": source_language,
        "target_language": target_language,
        "ai_provider": runtime_settings.get("ai_provider", "deepseek"),
        "use_fallback": False,
    }
    data = await _post("/v1/translate/context", payload, timeout=10.0)
    translation = data.get("translation")
    if not isinstance(translation, str):
        raise TranslationResponseError("Translation service response is missing translation")
    return translation


async def translate_in_context_with_fallback(
    word: str,
    sentence: str,
    source_language: str = "en",
    target_language: str = "zh-CN",
) -> TranslationResult:
    runtime_settings = _runtime_settings()
    payload = {
        "word": word,
        "sentence": sentence,
        "source_language": source_language,
        "target_language": target_language,
        "ai_provider": runtime_settings.get("ai_provider", "deepseek"),
        "use_fallback": bool(runtime_settings.get("use_free_translation_fallback", True)),
    }
    data = await _post("/v1/translate/context", payload, timeout=10.0)
    translation = data.get("translation")
    if not isinstance(translation, str):
        raise TranslationResponseError("Translation service response is missing translation")
    return TranslationResult(
        translation=translation,
        is_fallback=bool(data.get("is_fallback", False)),
    )


async def batch_translate_article(
    article_text: str,
    word_entries: Sequence[tuple[int, int, str]],
    sentences: Sequence[dict],
) -> dict[str, str]:
    runtime_settings = _runtime_settings()
    payload = {
        "article_text": article_text,
        "word_entries": [list(entry) for entry in word_entries],
        "sentences": list(sentences),
        "ai_provider": runtime_settings.get("ai_provider", "deepseek"),
    }
    data = await _post("/v1/translate/batch", payload, timeout=190.0)
    translations = data.get("translations")
    if not isinstance(translations, dict):
        raise TranslationResponseError("Translation service response is missing translations")
    return {str(key): str(value) for key, value in translations.items()}
```

- [ ] **Step 3: Run backend client tests to verify green**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/test_translation_engine_client.py -q
```

Expected: PASS.

- [ ] **Step 4: Run existing translation tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/test_translation_engine.py tests/test_batch_translation_keys.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit backend client implementation**

Run:

```bash
git add backend/app/config.py backend/app/services/translation_engine_service.py backend/tests/test_translation_engine_client.py
git commit -m "feat: call translation service from backend"
```

---

### Task 5: Dockerization

**Files:**
- Create: `translation-service/requirements.txt`
- Create: `translation-service/Dockerfile`
- Create: `backend/Dockerfile`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Add translation service requirements**

Create `translation-service/requirements.txt`:

```text
fastapi==0.110.3
uvicorn[standard]==0.29.0
pydantic-settings==2.2.1
httpx==0.27.0
google-genai>=1.0.0
openai>=1.0.0
deep-translator==1.11.4
pytest==8.2.2
```

- [ ] **Step 2: Add translation service Dockerfile**

Create `translation-service/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY translation-service/requirements.txt /app/translation-service/requirements.txt
RUN pip install --no-cache-dir -r /app/translation-service/requirements.txt

COPY backend/app/translation_engine /app/backend/app/translation_engine
COPY translation-service/translation_service /app/translation-service/translation_service

ENV PYTHONPATH=/app/translation-service:/app/backend/app
EXPOSE 8001

CMD ["uvicorn", "translation_service.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

- [ ] **Step 3: Add backend Dockerfile**

Create `backend/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend/app /app/backend/app

WORKDIR /app/backend
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 4: Update compose**

Replace `docker-compose.yml` with:

```yaml
services:
  db:
    image: postgres:16
    container_name: english_learning_db
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: english_learning
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  translation-service:
    build:
      context: .
      dockerfile: translation-service/Dockerfile
    environment:
      DEEPSEEK_API_KEY: ${DEEPSEEK_API_KEY:-}
      DEEPSEEK_MODEL: ${DEEPSEEK_MODEL:-deepseek-v4-flash}
      DEEPSEEK_BASE_URL: ${DEEPSEEK_BASE_URL:-https://api.deepseek.com}
      OPENAI_API_KEY: ${OPENAI_API_KEY:-}
      GEMINI_API_KEY: ${GEMINI_API_KEY:-}
    ports:
      - "8001:8001"

  backend:
    build:
      context: .
      dockerfile: backend/Dockerfile
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:postgres@db:5432/english_learning
      TRANSLATION_SERVICE_URL: http://translation-service:8001
      SECRET_KEY: ${SECRET_KEY:-change-this-in-production-use-env-var}
    ports:
      - "8000:8000"
    depends_on:
      - db
      - translation-service

volumes:
  postgres_data:
```

- [ ] **Step 5: Run focused non-Docker tests**

Run:

```bash
cd backend && PYTHONPATH=../translation-service:app .venv/bin/python -m pytest tests/test_translation_engine_client.py ../translation-service/tests/test_translation_service.py -q
```

Expected: PASS.

- [ ] **Step 6: Validate compose config**

Run:

```bash
docker compose config
```

Expected: exit 0 and rendered services include `db`, `backend`, and `translation-service`.

- [ ] **Step 7: Commit Dockerization**

Run:

```bash
git add translation-service/requirements.txt translation-service/Dockerfile backend/Dockerfile docker-compose.yml
git commit -m "chore: dockerize translation service"
```

---

### Task 6: Final Verification

**Files:**
- Verify only.

- [ ] **Step 1: Run translation engine unit tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/test_translation_engine.py tests/test_batch_translation_keys.py -q
```

Expected: PASS.

- [ ] **Step 2: Run backend client and service tests**

Run:

```bash
cd backend && PYTHONPATH=../translation-service:app .venv/bin/python -m pytest tests/test_translation_engine_client.py ../translation-service/tests/test_translation_service.py -q
```

Expected: PASS.

- [ ] **Step 3: Run cache/pretranslation regression tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/test_chunked_pretranslation.py tests/test_paragraph_articles.py tests/test_position_annotations.py tests/test_translation_recovery.py -q
```

Expected: PASS, or report any pre-existing database/environment failure with the exact error.

- [ ] **Step 4: Validate Docker compose**

Run:

```bash
docker compose config
```

Expected: exit 0.

- [ ] **Step 5: Report final branch state**

Run:

```bash
git status --short --branch
git log --oneline --decorate -n 8
```

Expected: clean working tree except expected branch ahead state.
