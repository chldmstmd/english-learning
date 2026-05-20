import asyncio
import json

from google import genai
from google.genai import types

from app.config import settings

_client = genai.Client(api_key=settings.gemini_api_key)

_TRANSLATION_CONFIG = types.GenerateContentConfig(
    thinking_config=types.ThinkingConfig(thinking_budget=0),
    response_mime_type="application/json",
    max_output_tokens=200,
    temperature=0.1,
)

_ANALYSIS_CONFIG = types.GenerateContentConfig(
    thinking_config=types.ThinkingConfig(thinking_budget=0),
    response_mime_type="application/json",
    max_output_tokens=500,
    temperature=0.3,
)

_BATCH_TRANSLATION_CONFIG = types.GenerateContentConfig(
    thinking_config=types.ThinkingConfig(thinking_budget=0),
    response_mime_type="application/json",
    max_output_tokens=16000,
    temperature=0.1,
)

_BATCH_TRANSLATION_PROMPT = (
    "你是专业英中词汇翻译助手。\n"
    "下面是一篇英文文章，以及文章中每个单词的位置信息。\n"
    "请根据上下文，为每个单词提供最符合语境的中文翻译（2-6个中文字）。\n"
    "对于虚词（the, a, is, are, was, were, be, to, of, in, on, at, for, and, or, but, "
    "that, this, it, not, no, do, does, did, have, has, had, will, would, can, could, "
    "shall, should, may, might, must）翻译为空字符串。\n\n"
    "返回JSON数组，每项格式：{{\"si\": 句子序号, \"wi\": 词序号, \"t\": \"翻译\"}}\n"
    "严格按照输入的位置列表顺序返回，不要遗漏任何一项。\n\n"
    "文章全文：\n{article_text}\n\n"
    "单词位置列表：\n{word_list}"
)

_TRANSLATION_PROMPT = (
    "你是专业英中词汇翻译助手。\n"
    "根据给定句子，为指定单词提供最符合当前语境的中文翻译。\n"
    "翻译控制在2-6个中文字以内。\n"
    '只返回JSON格式：{{"translation": "翻译结果"}}\n\n'
    "单词：{word}\n"
    "句子：{sentence}"
)

_ANALYSIS_PROMPT = (
    "你是英语词汇教学助手，为中文学习者解析英语单词用法。\n"
    "用1-3句中文解析该词在此句中的含义和用法，可提及词根、常见搭配或同义词。\n"
    '只返回JSON格式：{{"analysis": "解析内容"}}\n\n'
    "单词：{word}\n"
    "句子：{sentence}"
)

_MODEL = "gemini-2.5-flash"


async def translate_in_context(word: str, sentence: str) -> str:
    prompt = _TRANSLATION_PROMPT.format(word=word, sentence=sentence)
    response = await asyncio.wait_for(
        _client.aio.models.generate_content(
            model=_MODEL, contents=prompt, config=_TRANSLATION_CONFIG
        ),
        timeout=5.0,
    )
    result = json.loads(response.text)
    return result["translation"]


async def analyze_word(word: str, sentence: str) -> str:
    prompt = _ANALYSIS_PROMPT.format(word=word, sentence=sentence)
    response = await asyncio.wait_for(
        _client.aio.models.generate_content(
            model=_MODEL, contents=prompt, config=_ANALYSIS_CONFIG
        ),
        timeout=8.0,
    )
    result = json.loads(response.text)
    return result["analysis"]


async def batch_translate_article(article_text: str, words: list[dict]) -> list[dict]:
    """
    Translate all words in an article at once.
    words: [{"si": sentence_index, "wi": word_index, "w": word}]
    Returns: [{"si": int, "wi": int, "t": str}]
    """
    word_list_str = json.dumps(words, ensure_ascii=False)
    prompt = _BATCH_TRANSLATION_PROMPT.format(
        article_text=article_text, word_list=word_list_str
    )
    response = await asyncio.wait_for(
        _client.aio.models.generate_content(
            model=_MODEL, contents=prompt, config=_BATCH_TRANSLATION_CONFIG
        ),
        timeout=60.0,
    )
    result = json.loads(response.text)
    return result
