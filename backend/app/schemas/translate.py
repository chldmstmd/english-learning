from pydantic import BaseModel


class TranslateRequest(BaseModel):
    word: str    # surface form (e.g. "banks")
    lemma: str   # lowercase lemma used for annotation lookup (e.g. "bank")
    sentence: str
    article_id: str
    sentence_index: int  # clicked token position (annotation key + cache lookup)
    word_index: int      # clicked token position (annotation key + cache lookup)


class TranslateResponse(BaseModel):
    word: str
    lemma: str
    translation: str
    is_fallback: bool
