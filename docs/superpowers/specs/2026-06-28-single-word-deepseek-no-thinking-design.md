# Single Word DeepSeek No Thinking Design

## Goal

Improve uncached single-word translation latency by disabling DeepSeek thinking mode only for realtime click translations.

## Context

The current `/api/v1/translate-word` miss path calls `TranslationEngine.translate_in_context_with_fallback()`, which builds a small JSON prompt and sends it through `OpenAICompatibleProvider`. With `DEEPSEEK_MODEL=deepseek-v4-flash`, direct benchmark samples showed default single-word requests producing reasoning tokens and taking about 1.5 seconds. The same request with `extra_body={"thinking": {"type": "disabled"}}` returned the same translation without reasoning tokens and took about 1.0 seconds.

## Design

Add an optional provider-level extra body for single requests to `OpenAICompatibleProvider`. Configure it only for the DeepSeek provider in `translation_engine_service.py`; leave the OpenAI provider and Gemini provider unchanged.

The translate engine API does not need a new argument. It already marks realtime word calls as `request_kind="single"` and batch article calls as `request_kind="batch"`, so the provider can attach the DeepSeek-specific option based on request kind.

## Non-Goals

- Do not change batch translation behavior.
- Do not change the prompt or response schema.
- Do not add a user-facing setting unless later benchmarking shows a need.
- Do not switch providers or models.

## Testing

Add provider tests that use a fake OpenAI-compatible client and assert:

- single requests include `extra_body={"thinking": {"type": "disabled"}}` when the provider is configured with that option;
- batch requests omit that extra body;
- default OpenAI-compatible providers still omit extra body.

Run the focused translation engine test file after implementation.
