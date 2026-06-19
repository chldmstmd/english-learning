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
    chapter_count: int = 0          # populated per-request
    read_chapter_order: int | None = None   # which chapter the user last read (1-based order)

    model_config = {"from_attributes": True}


class ChapterListItem(BaseModel):
    id: str
    title: str
    chapter_order: int
    word_count: int
    last_sentence_index: int | None = None   # per-user resume position within this chapter

    model_config = {"from_attributes": True}


class BookDetailResponse(BaseModel):
    id: str
    title: str
    cover_image_url: str | None
    source_category: str | None
    created_at: datetime
    chapters: list[ChapterListItem]
    # Resume target: the chapter article_id to continue from, or null if unread
    continue_article_id: str | None = None
    continue_sentence_index: int | None = None
