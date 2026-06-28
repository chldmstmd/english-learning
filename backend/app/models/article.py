from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import String, Text, Integer, DateTime, Index, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (
        Index("ix_articles_tokens_gin", "tokens", postgresql_using="gin"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    # [{"text":"The","pos":"DT","lemma":"the","index":0,"sentence_index":0,"is_punct":false,"is_alpha":true,"ws":" "}]
    tokens: Mapped[list] = mapped_column(JSONB, nullable=False)
    # [{"index":0,"text":"The bank of the river..."}]
    sentences: Mapped[list] = mapped_column(JSONB, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Batch translation status: untranslated | processing | done | stale | failed
    translation_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="untranslated"
    )
    translation_total_words: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )
    translation_processed_words: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )
    translation_total_chunks: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )
    translation_completed_chunks: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )

    @property
    def translation_progress(self) -> dict:
        total_words = self.translation_total_words or 0
        processed_words = min(self.translation_processed_words or 0, total_words)
        percent = int(processed_words * 100 / total_words) if total_words else 0
        if self.translation_status == "done" and total_words == 0:
            percent = 100
        return {
            "total_words": total_words,
            "processed_words": processed_words,
            "total_chunks": self.translation_total_chunks or 0,
            "completed_chunks": min(
                self.translation_completed_chunks or 0,
                self.translation_total_chunks or 0,
            ),
            "percent": percent,
        }
