from __future__ import annotations

from collections import defaultdict
from typing import Sequence

TRANSLATION_PROMPT = (
    "按语境把单词从{source_language}翻译成{target_language}。"
    "目标是中文(zh/zh-CN/Chinese)时用2-6个中文字；否则简短自然。"
    '只返回JSON:{{"translation":"..."}}\n'
    "单词:{word}\n"
    "句子:{sentence}"
)

BATCH_TRANSLATION_PROMPT = (
    "你是专业英中词汇翻译助手。\n"
    "下面是一篇英文文章，以及按句子分组的待翻译词汇。\n"
    "每个待翻译词汇的格式为 \"词汇ID: 单词\"，词汇ID形如\"0_1\"。\n"
    "根据每个词所在句子的上下文，提供最准确的中文翻译（2-6个中文字）。\n"
    "虚词（冠词、介词、系动词、助动词、代词等）翻译为空字符串\"\"。\n\n"
    "以JSON对象返回结果，key为词汇ID（如\"0_1\"），value为翻译字符串。\n"
    "每个词汇ID必须有对应的key，不可遗漏。只返回JSON，不要其他内容。\n\n"
    "文章全文（供整体理解）：\n{article_text}\n\n"
    "待翻译词汇（按句子分组）：\n{sentence_blocks}"
)


def build_sentence_blocks(
    word_entries: Sequence[tuple[int, int, str]],
    sentences: Sequence[dict],
) -> str:
    """Render the sentence-grouped word list for the batch prompt."""
    by_sentence: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for sentence_index, word_index, text in word_entries:
        by_sentence[sentence_index].append((word_index, text))

    sentence_text_map = {sentence["index"]: sentence["text"] for sentence in sentences}

    blocks = []
    for sentence_index in sorted(by_sentence):
        sentence_text = sentence_text_map.get(sentence_index, "")
        words_repr = ", ".join(
            f'"{sentence_index}_{word_index}": {text}'
            for word_index, text in sorted(by_sentence[sentence_index])
        )
        blocks.append(f'句子{sentence_index}（"{sentence_text}"）：{words_repr}')
    return "\n".join(blocks)
