from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class BookCreateRequest(BaseModel):
    title: str
    cover_image_url: str | None = None
    source_category: str | None = None


class ChapterCreateRequest(BaseModel):
    title: str
    raw_text: str


class BookListItem(BaseModel):
    id: str
    title: str
    cover_image_url: str | None
    source_category: str | None
    created_at: datetime
    chapter_count: int = 0
    read_chapter_order: int | None = None
    is_from_library: bool = False

    model_config = {"from_attributes": True}


class ChapterListItem(BaseModel):
    id: str
    title: str
    chapter_order: int
    word_count: int
    last_sentence_index: int | None = None
    translation_status: Literal["untranslated", "processing", "done", "stale", "failed"] = "untranslated"

    model_config = {"from_attributes": True}


class AdminChapterListItem(BaseModel):
    """Admin chapter listing — includes raw_text so the admin UI can edit in place."""
    id: str
    title: str
    chapter_order: int
    word_count: int
    translation_status: Literal["untranslated", "processing", "done", "stale", "failed"] = "untranslated"
    raw_text: str = ""

    model_config = {"from_attributes": True}


class BookDetailResponse(BaseModel):
    id: str
    title: str
    cover_image_url: str | None
    source_category: str | None
    created_at: datetime
    chapters: list[ChapterListItem]
    continue_article_id: str | None = None
    continue_sentence_index: int | None = None
    is_owner: bool = False
    is_library: bool = False


class LibraryBookListItem(BaseModel):
    id: str
    title: str
    cover_image_url: str | None = None
    source_category: str | None = None
    created_at: datetime
    chapter_count: int = 0          # populated per-request
    is_saved: bool = False          # populated per-request

    model_config = {"from_attributes": True}


class ChapterPatchRequest(BaseModel):
    title: str | None = None
    raw_text: str | None = None


class BookPatchRequest(BaseModel):
    title: str | None = None
    cover_image_url: str | None = None
    source_category: str | None = None
