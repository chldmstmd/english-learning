from datetime import datetime
from uuid import uuid4

from sqlalchemy import String, Text, DateTime, Integer, Float, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Vocabulary(Base):
    __tablename__ = "vocabulary"
    __table_args__ = (
        UniqueConstraint("user_id", "word", name="uq_vocab_user_word"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    word: Mapped[str] = mapped_column(String(100), nullable=False)  # lowercase lemma
    pos: Mapped[str | None] = mapped_column(String(20), nullable=True)
    context_translation: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_sentence: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    mastered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Post-MVP: spaced repetition fields (reserved, unused in V1)
    interval: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ease_factor: Mapped[float | None] = mapped_column(Float, nullable=True)
    next_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
