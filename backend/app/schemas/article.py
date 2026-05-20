from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ArticleCreateRequest(BaseModel):
    title: str
    raw_text: str


class ArticleListItem(BaseModel):
    id: str
    title: str
    word_count: int
    created_at: datetime
    # Present for bookmarked library articles in the unified list
    is_library: bool = False
    source_category: str | None = None
    difficulty: str | None = None

    model_config = {"from_attributes": True}


class LibraryArticleListItem(BaseModel):
    id: str
    title: str
    word_count: int
    source_category: str | None
    difficulty: str | None
    published_at: datetime | None
    cover_image_url: str | None
    source_url: str | None
    created_at: datetime
    # Populated per-request by the router (not ORM fields)
    is_bookmarked: bool = False
    read_at: datetime | None = None

    model_config = {"from_attributes": True}


class AnnotationSchema(BaseModel):
    translation: str | None
    source_sentence: str | None
    is_fallback: bool
    gen_status: str


class ArticleDetailResponse(BaseModel):
    id: str
    title: str
    tokens: list[dict[str, Any]]
    sentences: list[dict[str, Any]]
    word_count: int
    annotations: dict[str, AnnotationSchema]  # lemma → annotation
    word_statuses: dict[str, str]             # lemma → status
    # Library metadata (null for user-uploaded articles)
    is_library: bool = False
    is_bookmarked: bool = False
    source_url: str | None = None
    source_category: str | None = None
    difficulty: str | None = None
    published_at: datetime | None = None
    translation_status: str = "pending"

    model_config = {"from_attributes": True}
