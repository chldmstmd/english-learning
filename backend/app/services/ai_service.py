from __future__ import annotations

from typing import Sequence

from app.services.translation_engine_service import (
    batch_translate_article as _batch_translate_article,
    translate_in_context as _translate_in_context,
)
from app.translation_engine import (
    build_sentence_blocks,
)

# Compatibility layer for existing imports. New code should import from
# app.translation_engine directly.
_build_sentence_blocks = build_sentence_blocks


async def translate_in_context(word: str, sentence: str) -> str:
    return await _translate_in_context(word, sentence)


async def batch_translate_article(
    article_text: str,
    word_entries: Sequence[tuple[int, int, str]],
    sentences: Sequence[dict],
) -> dict[str, str]:
    return await _batch_translate_article(article_text, word_entries, sentences)
