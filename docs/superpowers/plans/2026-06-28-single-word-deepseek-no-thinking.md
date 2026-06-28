# Single Word DeepSeek No Thinking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Disable DeepSeek thinking mode for uncached realtime single-word translation requests.

**Architecture:** Keep `TranslationEngine` unchanged and add an optional single-request body hook inside `OpenAICompatibleProvider`. Configure only the DeepSeek provider with `{"thinking": {"type": "disabled"}}`; batch translation and other providers keep their existing request payloads.

**Tech Stack:** FastAPI backend, Python async provider layer, pytest.

---

### Task 1: Provider Contract Test

**Files:**
- Modify: `backend/tests/test_translation_engine.py`

- [x] **Step 1: Write the failing tests**

Add fake OpenAI-compatible client helpers and these tests:

```python
from app.translation_engine import OpenAICompatibleProvider


class FakeOpenAIMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeOpenAIChoice:
    def __init__(self, content: str) -> None:
        self.message = FakeOpenAIMessage(content)


class FakeOpenAIResponse:
    def __init__(self, content: str) -> None:
        self.choices = [FakeOpenAIChoice(content)]


class FakeOpenAICompletions:
    def __init__(self, content: str = '{"translation": "河岸"}') -> None:
        self.content = content
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeOpenAIResponse(self.content)


class FakeOpenAIChat:
    def __init__(self, completions: FakeOpenAICompletions) -> None:
        self.completions = completions


class FakeOpenAIClient:
    def __init__(self, completions: FakeOpenAICompletions) -> None:
        self.chat = FakeOpenAIChat(completions)
```

```python
def test_openai_compatible_provider_adds_extra_body_to_single_requests():
    completions = FakeOpenAICompletions()
    provider = OpenAICompatibleProvider(
        api_key_getter=lambda: "key",
        model_getter=lambda: "model",
        single_request_extra_body={"thinking": {"type": "disabled"}},
    )
    provider._client = FakeOpenAIClient(completions)

    result = asyncio.run(
        provider.complete_json(
            "prompt",
            max_tokens=100,
            temperature=0,
            timeout=1,
            request_kind="single",
        )
    )

    assert result == '{"translation": "河岸"}'
    assert completions.calls[0]["extra_body"] == {"thinking": {"type": "disabled"}}
```

```python
def test_openai_compatible_provider_omits_single_extra_body_for_batch_requests():
    completions = FakeOpenAICompletions()
    provider = OpenAICompatibleProvider(
        api_key_getter=lambda: "key",
        model_getter=lambda: "model",
        single_request_extra_body={"thinking": {"type": "disabled"}},
    )
    provider._client = FakeOpenAIClient(completions)

    asyncio.run(
        provider.complete_json(
            "prompt",
            max_tokens=16000,
            temperature=0.1,
            timeout=1,
            request_kind="batch",
        )
    )

    assert "extra_body" not in completions.calls[0]
```

```python
def test_openai_compatible_provider_omits_extra_body_by_default():
    completions = FakeOpenAICompletions()
    provider = OpenAICompatibleProvider(
        api_key_getter=lambda: "key",
        model_getter=lambda: "model",
    )
    provider._client = FakeOpenAIClient(completions)

    asyncio.run(
        provider.complete_json(
            "prompt",
            max_tokens=100,
            temperature=0,
            timeout=1,
            request_kind="single",
        )
    )

    assert "extra_body" not in completions.calls[0]
```

- [x] **Step 2: Run tests to verify failure**

Run: `cd backend && .venv/bin/python -m pytest tests/test_translation_engine.py -q`

Expected: FAIL because `OpenAICompatibleProvider.__init__()` does not accept `single_request_extra_body`.

### Task 2: Provider Implementation

**Files:**
- Modify: `backend/app/translation_engine/providers.py`
- Modify: `backend/app/services/translation_engine_service.py`

- [x] **Step 1: Implement optional single request extra body**

In `OpenAICompatibleProvider.__init__`, add:

```python
single_request_extra_body: dict[str, Any] | None = None,
```

Store it:

```python
self._single_request_extra_body = single_request_extra_body
```

In `complete_json`, build request kwargs before calling `create()`:

```python
request_kwargs = {
    "model": self._model_getter(),
    "messages": [{"role": "user", "content": prompt}],
    "max_tokens": max_tokens,
    "temperature": temperature,
    "response_format": {"type": "json_object"},
}
if request_kind == "single" and self._single_request_extra_body is not None:
    request_kwargs["extra_body"] = self._single_request_extra_body
```

Then call:

```python
self._get_client().chat.completions.create(**request_kwargs)
```

- [x] **Step 2: Configure DeepSeek only**

In `create_default_translation_engine()`, pass this option only to the `"deepseek"` provider:

```python
single_request_extra_body={"thinking": {"type": "disabled"}},
```

- [x] **Step 3: Run focused tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_translation_engine.py -q`

Expected: PASS.

### Task 3: Documentation and Verification

**Files:**
- Modify: `docs/translation-engine-spec.md`

- [x] **Step 1: Document the realtime DeepSeek request option**

Update the single-word provider behavior section to mention that the default DeepSeek provider disables thinking mode for `request_kind="single"` only.

- [x] **Step 2: Run focused tests again**

Run: `cd backend && .venv/bin/python -m pytest tests/test_translation_engine.py -q`

Expected: PASS.

- [x] **Step 3: Optional live latency smoke**

Run a one-off DeepSeek request through `translate_in_context("bank", "The boat reached the bank of the river.")` and confirm the result is `"河岸"` or equivalent and does not error.
