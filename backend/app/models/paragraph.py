from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ParagraphVersion(Base):
    __tablename__ = "paragraph_versions"
    __table_args__ = (
        Index("ix_paragraph_versions_text_hash", "text_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    tokens: Mapped[list] = mapped_column(JSONB, nullable=False)
    sentences: Mapped[list] = mapped_column(JSONB, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ArticleParagraph(Base):
    __tablename__ = "article_paragraphs"
    __table_args__ = (
        UniqueConstraint("article_id", "position", name="uq_article_paragraph_position"),
        Index("ix_article_paragraphs_article_position", "article_id", "position"),
        Index("ix_article_paragraphs_paragraph_version_id", "paragraph_version_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    article_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("articles.id", ondelete="CASCADE"), nullable=False
    )
    paragraph_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("paragraph_versions.id"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ParagraphTranslation(Base):
    __tablename__ = "paragraph_translations"
    __table_args__ = (
        UniqueConstraint(
            "paragraph_version_id",
            "sentence_index",
            "word_index",
            name="uq_paragraph_word_position",
        ),
        Index("ix_paragraph_translations_paragraph_version_id", "paragraph_version_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paragraph_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("paragraph_versions.id", ondelete="CASCADE"), nullable=False
    )
    sentence_index: Mapped[int] = mapped_column(Integer, nullable=False)
    word_index: Mapped[int] = mapped_column(Integer, nullable=False)
    word: Mapped[str] = mapped_column(String(100), nullable=False)
    lemma: Mapped[str] = mapped_column(String(100), nullable=False)
    translation: Mapped[str] = mapped_column(Text, nullable=False)


class ParagraphAnnotation(Base):
    __tablename__ = "paragraph_annotations"
    __table_args__ = (
        UniqueConstraint(
            "article_id",
            "user_id",
            "article_paragraph_id",
            "sentence_index",
            "word_index",
            name="uq_paragraph_annotation_position",
        ),
        Index("ix_paragraph_annotations_article_user", "article_id", "user_id"),
        Index("ix_paragraph_annotations_article_paragraph_id", "article_paragraph_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    article_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("articles.id", ondelete="CASCADE"), nullable=False
    )
    article_paragraph_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("article_paragraphs.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    sentence_index: Mapped[int] = mapped_column(Integer, nullable=False)
    word_index: Mapped[int] = mapped_column(Integer, nullable=False)
    word: Mapped[str] = mapped_column(String(100), nullable=False)
    translation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_sentence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    gen_status: Mapped[str] = mapped_column(String(20), nullable=False, default="done")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
