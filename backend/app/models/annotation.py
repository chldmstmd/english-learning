from datetime import datetime
from uuid import uuid4

from sqlalchemy import String, Text, Boolean, DateTime, UniqueConstraint, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ArticleAnnotation(Base):
    __tablename__ = "article_annotations"
    __table_args__ = (
        UniqueConstraint("article_id", "user_id", "word", name="uq_annotation_article_user_word"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    article_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    word: Mapped[str] = mapped_column(String(100), nullable=False)
    translation: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_sentence: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # pending → done | failed
    gen_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
