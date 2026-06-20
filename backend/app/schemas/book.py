from datetime import datetime

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


class LibraryBookListItem(BaseModel):
    id: str
    title: str
    cover_image_url: str | None = None
    source_category: str | None = None
    created_at: datetime
    chapter_count: int = 0          # populated per-request
    is_saved: bool = False          # populated per-request

    model_config = {"from_attributes": True}
