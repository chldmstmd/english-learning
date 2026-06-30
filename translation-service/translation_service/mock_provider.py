from __future__ import annotations

import json
import re

from translation_engine.providers import RequestKind


class MockTranslationProvider:
    async def complete_json(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        timeout: float,
        request_kind: RequestKind,
    ) -> str:
        if request_kind == "batch":
            return json.dumps(_extract_batch_translations(prompt), ensure_ascii=False)
        return json.dumps(
            {"translation": _mock_translation(_extract_single_word(prompt))},
            ensure_ascii=False,
        )


def _mock_translation(word: str) -> str:
    return f"mock: {word.strip()}"


def _extract_single_word(prompt: str) -> str:
    match = re.search(r"^单词:(?P<word>.+?)$", prompt, flags=re.MULTILINE)
    return match.group("word").strip() if match else "unknown"


def _extract_batch_translations(prompt: str) -> dict[str, str]:
    entries = re.findall(r'"(?P<key>\d+_\d+)":\s*(?P<word>[^,\n]+)', prompt)
    return {key: _mock_translation(word) for key, word in entries}
