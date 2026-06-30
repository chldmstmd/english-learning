from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel


class ArticleCreateRequest(BaseModel):
    title: str
    raw_text: str


class ArticleUpdateRequest(BaseModel):
    title: str
    raw_text: str


class ProgressUpdateRequest(BaseModel):
    last_sentence_index: int


class TranslationProgress(BaseModel):
    total_words: int = 0
    processed_words: int = 0
    total_chunks: int = 0
    completed_chunks: int = 0
    percent: int = 0


class ArticleListItem(BaseModel):
    id: str
    title: str
    word_count: int
    created_at: datetime
    translation_status: Literal["untranslated", "processing", "done", "stale", "failed"] = "untranslated"
    translation_progress: TranslationProgress

    model_config = {"from_attributes": True}


class AnnotationSchema(BaseModel):
    translation: Optional[str]
    source_sentence: Optional[str]
    is_fallback: bool
    gen_status: str


class ArticleParagraphSchema(BaseModel):
    id: str
    paragraph_version_id: str
    position: int
    raw_text: str
    tokens: list[dict[str, Any]]
    sentences: list[dict[str, Any]]
    word_count: int


class ArticleDetailResponse(BaseModel):
    id: str
    title: str
    raw_text: str
    tokens: list[dict[str, Any]]
    sentences: list[dict[str, Any]]
    paragraphs: list[ArticleParagraphSchema]
    word_count: int
    annotations: dict[str, AnnotationSchema]
    translation_status: Literal["untranslated", "processing", "done", "stale", "failed"] = "untranslated"
    translation_progress: TranslationProgress
    last_sentence_index: Optional[int] = None

    model_config = {"from_attributes": True}


class ArticleTranslateResponse(BaseModel):
    translation_status: Literal["untranslated", "processing", "done", "stale", "failed"]
    translation_progress: TranslationProgress
