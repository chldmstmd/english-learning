from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, Text, Boolean, Integer, DateTime, UniqueConstraint, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ArticleAnnotation(Base):
    __tablename__ = "article_annotations"
    __table_args__ = (
        UniqueConstraint(
            "article_id", "user_id", "sentence_index", "word_index",
            name="uq_annotation_position",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    article_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    sentence_index: Mapped[int] = mapped_column(Integer, nullable=False)
    word_index: Mapped[int] = mapped_column(Integer, nullable=False)
    word: Mapped[str] = mapped_column(String(100), nullable=False)  # lemma at this position
    translation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_sentence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # always "done" under per-instance model (no more pending pre-seeding); kept for type compat
    gen_status: Mapped[str] = mapped_column(String(20), nullable=False, default="done")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
