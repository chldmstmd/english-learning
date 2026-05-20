from datetime import datetime
from uuid import uuid4

from sqlalchemy import String, Text, Integer, DateTime, Boolean, Index, func
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

    # V1.1: Content library fields (null for user-uploaded articles)
    # source: "user_upload" | "voa"
    source: Mapped[str] = mapped_column(String(32), nullable=False, server_default="user_upload")
    # is_library=True means public shared article; False means user's private article
    is_library: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    source_category: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # difficulty: "level1" (slow) | "level2" (standard)
    difficulty: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cover_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Batch translation status: pending | processing | done | failed
    translation_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="pending"
    )
