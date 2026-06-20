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

_BATCH_TRANSLATION_PROMPT = (
    "你是专业英中词汇翻译助手。\n"
    "下面是一篇英文文章，以及按句子分组的待翻译词汇。\n"
    "根据每个词所在句子的上下文，提供最准确的中文翻译（2-6个中文字）。\n"
    "虚词（冠词、介词、系动词、助动词、代词等）翻译为空字符串\"\"。\n\n"
    "以JSON对象返回结果，key格式为\"句子序号_词序号\"（如\"0_1\"），value为翻译字符串。\n"
    "每个词必须有对应的key，不可遗漏。只返回JSON，不要其他内容。\n\n"
    "文章全文（供整体理解）：\n{article_text}\n\n"
    "待翻译词汇（按句子分组）：\n{sentence_blocks}"
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


async def batch_translate_article(
    article_text: str,
    word_entries: list[tuple[int, int, str]],  # [(sentence_index, word_index, text), ...]
    sentences: list[dict],                      # [{"index": 0, "text": "..."}, ...]
) -> dict[str, str]:
    """
    Translate all words in an article using sentence-grouped context.
    Returns dict mapping "si_wi" keys to translation strings.
    """
    # Group words by sentence
    from collections import defaultdict
    by_sentence: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for si, wi, text in word_entries:
        by_sentence[si].append((wi, text))

    sentence_text_map = {s["index"]: s["text"] for s in sentences}

    # Build the sentence-grouped block
    blocks = []
    for si in sorted(by_sentence):
        sentence_text = sentence_text_map.get(si, "")
        words_repr = ", ".join(f'"{wi}_{text}"' for wi, text in sorted(by_sentence[si]))
        blocks.append(f'句子{si}（"{sentence_text}"）：{words_repr}')
    sentence_blocks = "\n".join(blocks)

    prompt = _BATCH_TRANSLATION_PROMPT.format(
        article_text=article_text,
        sentence_blocks=sentence_blocks,
    )
    provider = _get_provider()

    if provider == "openai":
        text = await _openai_chat(prompt, max_tokens=16000, temperature=0.1, timeout=180.0)
        result = json.loads(text)
    else:
        response = await asyncio.wait_for(
            _gemini_client.aio.models.generate_content(
                model=_GEMINI_MODEL, contents=prompt, config=_GEMINI_BATCH_CONFIG
            ),
            timeout=60.0,
        )
        result = json.loads(response.text)

    # Normalise: keys may come back as "si_wi" or nested; flatten to "si_wi" -> str
    if not isinstance(result, dict):
        raise ValueError(f"Expected dict response, got {type(result)}")
    return {str(k): str(v) for k, v in result.items()}
