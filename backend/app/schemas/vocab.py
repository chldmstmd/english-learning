from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class VocabItem(BaseModel):
    id: str
    word: str
    pos: str | None
    context_translation: str | None
    status: str
    created_at: datetime
    mastered_at: datetime | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class VocabStatusUpdate(BaseModel):
    status: Literal["new", "reviewing", "mastered"]


class VocabDetailResponse(BaseModel):
    word: str
    phonetic: str | None
    status: str
    context_translation: str | None
    source_sentence: str | None
    definitions: list[dict]
