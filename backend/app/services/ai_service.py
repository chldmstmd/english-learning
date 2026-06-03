import asyncio
import json

from google import genai
from google.genai import types
from openai import AsyncOpenAI

from app.config import settings
from app.services import settings_service

# --- Gemini client ---
_gemini_client = genai.Client(api_key=settings.gemini_api_key)

_GEMINI_TRANSLATION_CONFIG = types.GenerateContentConfig(
    thinking_config=types.ThinkingConfig(thinking_budget=0),
    response_mime_type="application/json",
    max_output_tokens=200,
    temperature=0.1,
)

_GEMINI_ANALYSIS_CONFIG = types.GenerateContentConfig(
    thinking_config=types.ThinkingConfig(thinking_budget=0),
    response_mime_type="application/json",
    max_output_tokens=500,
    temperature=0.3,
)

_GEMINI_BATCH_CONFIG = types.GenerateContentConfig(
    thinking_config=types.ThinkingConfig(thinking_budget=0),
    response_mime_type="application/json",
    max_output_tokens=16000,
    temperature=0.1,
)

_GEMINI_MODEL = "models/gemini-3.5-flash"
_GEMINI_LITE_MODEL = "models/gemini-3.1-flash-lite"

# --- Prompts (shared between providers) ---

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

_BATCH_TRANSLATION_PROMPT = (
    "你是专业英中词汇翻译助手。\n"
    "下面是一篇英文文章和按顺序排列的单词列表。\n"
    "请根据上下文，为每个单词提供最符合语境的中文翻译（2-6个中文字）。\n"
    "对于虚词（the, a, is, are, was, were, be, to, of, in, on, at, for, and, or, but, "
    "that, this, it, not, no, do, does, did, have, has, had, will, would, can, could, "
    "shall, should, may, might, must, if, you, we, they, he, she, his, her, its, "
    "my, your, our, their, me, him, us, them, an, so, as）翻译为空字符串。\n\n"
    "严格按照输入顺序返回一个JSON数组，数组长度必须等于单词数量（{word_count}个），"
    "每项是对应单词的翻译字符串。不要遗漏任何一项。\n\n"
    "文章全文：\n{article_text}\n\n"
    "单词列表（共{word_count}个）：\n{word_list}"
)

# --- OpenAI client ---

_openai_client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
_OPENAI_MODEL = "gpt-4o"


async def _openai_chat(prompt: str, max_tokens: int = 200, temperature: float = 0.1, timeout: float = 30.0) -> str:
    """Call OpenAI chat completion API and return the content string."""
    response = await asyncio.wait_for(
        _openai_client.chat.completions.create(
            model=_OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
            response_format={"type": "json_object"},
        ),
        timeout=timeout,
    )
    return response.choices[0].message.content


# --- Provider selection ---

def _get_provider() -> str:
    """Get current AI provider from settings. Default: gemini."""
    return settings_service.load().get("ai_provider", "gemini")


# --- Public API ---

async def translate_in_context(word: str, sentence: str) -> str:
    prompt = _TRANSLATION_PROMPT.format(word=word, sentence=sentence)
    provider = _get_provider()

    if provider == "openai":
        text = await _openai_chat(prompt, max_tokens=200, temperature=0.1, timeout=5.0)
    else:
        response = await asyncio.wait_for(
            _gemini_client.aio.models.generate_content(
                model=_GEMINI_LITE_MODEL, contents=prompt, config=_GEMINI_TRANSLATION_CONFIG
            ),
            timeout=5.0,
        )
        text = response.text

    result = json.loads(text)
    return result["translation"]


async def analyze_word(word: str, sentence: str) -> str:
    prompt = _ANALYSIS_PROMPT.format(word=word, sentence=sentence)
    provider = _get_provider()

    if provider == "openai":
        text = await _openai_chat(prompt, max_tokens=500, temperature=0.3, timeout=8.0)
    else:
        response = await asyncio.wait_for(
            _gemini_client.aio.models.generate_content(
                model=_GEMINI_MODEL, contents=prompt, config=_GEMINI_ANALYSIS_CONFIG
            ),
            timeout=8.0,
        )
        text = response.text

    result = json.loads(text)
    return result["analysis"]


async def batch_translate_article(article_text: str, word_texts: list[str]) -> list[str]:
    """
    Translate all words in an article at once.
    word_texts: ordered list of word surface forms (e.g. ["The", "scientists", "discovered", ...])
    Returns: ordered list of translations (same length as input), empty string for function words.
    """
    word_list_str = json.dumps(word_texts, ensure_ascii=False)
    prompt = _BATCH_TRANSLATION_PROMPT.format(
        article_text=article_text,
        word_list=word_list_str,
        word_count=len(word_texts),
    )
    provider = _get_provider()

    if provider == "openai":
        # OpenAI json_object mode requires object, not array
        openai_prompt = prompt + '\n\n注意：将结果包装为JSON对象格式：{"translations": [...]}'
        text = await _openai_chat(openai_prompt, max_tokens=16000, temperature=0.1, timeout=180.0)
        parsed = json.loads(text)
        translations = parsed["translations"] if isinstance(parsed, dict) else parsed
    else:
        response = await asyncio.wait_for(
            _gemini_client.aio.models.generate_content(
                model=_GEMINI_MODEL, contents=prompt, config=_GEMINI_BATCH_CONFIG
            ),
            timeout=60.0,
        )
        translations = json.loads(response.text)

    # Validate length
    if len(translations) != len(word_texts):
        raise ValueError(
            f"Translation count mismatch: expected {len(word_texts)}, got {len(translations)}"
        )
    return translations
