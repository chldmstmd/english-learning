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
