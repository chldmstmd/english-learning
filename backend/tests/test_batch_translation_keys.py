"""
Regression tests for batch-translation key alignment.

The batch prompt lists each word to translate and asks the AI to return a JSON
object keyed by those identifiers; the write-back path then reads each value by
the "{sentence_index}_{word_index}" key. A previous version listed the words as
"{word_index}_{text}" (e.g. "2_large") while instructing the model to key by
"{sentence_index}_{word_index}" (e.g. "0_2"). The two namespaces never matched,
so every lookup missed and all 276 cached translations were written empty —
making "translated" articles silently fall back to live AI calls per word.

These lock the contract: the identifiers advertised in the prompt are exactly
the "{si}_{wi}" keys the caller reads back.
"""
import re

from app.translation_engine.prompts import BATCH_TRANSLATION_PROMPT, build_sentence_blocks


def test_block_advertises_si_wi_keys():
    # sentence 0 has words at indices 0 and 2; sentence 1 has a word at index 5
    word_entries = [(0, 0, "Pumas"), (0, 2, "large"), (1, 5, "reports")]
    sentences = [
        {"index": 0, "text": "Pumas are large."},
        {"index": 1, "text": "When reports came."},
    ]

    block = build_sentence_blocks(word_entries, sentences)

    # The si_wi identifiers the write-back path uses must appear verbatim
    assert '"0_0"' in block
    assert '"0_2"' in block
    assert '"1_5"' in block

    # The old buggy "{wi}_{text}" identifiers must NOT appear
    assert "0_Pumas" not in block
    assert "2_large" not in block
    assert "5_reports" not in block


def test_every_word_entry_has_a_distinct_si_wi_identifier():
    word_entries = [(0, 0, "a"), (0, 1, "b"), (1, 0, "c")]
    sentences = [{"index": 0, "text": "a b"}, {"index": 1, "text": "c"}]

    block = build_sentence_blocks(word_entries, sentences)

    ids = set(re.findall(r'"(\d+_\d+)"', block))
    assert ids == {"0_0", "0_1", "1_0"}


def test_batch_prompt_requires_token_level_translations():
    assert "逐词ruby标注" in BATCH_TRANSLATION_PROMPT
    assert "只翻译该ID对应的单词本身" in BATCH_TRANSLATION_PROMPT
    assert "不要翻译包含它的相邻短语" in BATCH_TRANSLATION_PROMPT
    assert "University=大学" in BATCH_TRANSLATION_PROMPT
    assert "Press=出版社" in BATCH_TRANSLATION_PROMPT
