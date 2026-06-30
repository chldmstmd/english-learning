from __future__ import annotations

from pydantic import BaseModel, Field


class ContextTranslationRequest(BaseModel):
    word: str
    sentence: str
    source_language: str = "en"
    target_language: str = "zh-CN"
    ai_provider: str = "deepseek"
    use_fallback: bool = True


class ContextTranslationResponse(BaseModel):
    translation: str
    is_fallback: bool = False


class SentenceBlock(BaseModel):
    index: int
    text: str


class BatchTranslationRequest(BaseModel):
    article_text: str
    word_entries: list[tuple[int, int, str]] = Field(default_factory=list)
    sentences: list[SentenceBlock] = Field(default_factory=list)
    ai_provider: str = "deepseek"


class BatchTranslationResponse(BaseModel):
    translations: dict[str, str]
