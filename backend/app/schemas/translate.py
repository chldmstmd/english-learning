from pydantic import BaseModel


class TranslateRequest(BaseModel):
    word: str    # surface form (e.g. "banks")
    lemma: str   # lowercase lemma used as vocab key (e.g. "bank")
    sentence: str
    article_id: str


class TranslateResponse(BaseModel):
    word: str
    lemma: str
    translation: str
    is_fallback: bool
    status: str  # current vocab status after upsert
