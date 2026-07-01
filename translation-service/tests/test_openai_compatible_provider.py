from __future__ import annotations

import asyncio

from translation_engine import OpenAICompatibleProvider


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
