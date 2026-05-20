from sqlalchemy import String, Text, Integer, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ArticleTranslation(Base):
    __tablename__ = "article_translations"
    __table_args__ = (
        UniqueConstraint("article_id", "sentence_index", "word_index", name="uq_article_word_position"),
        Index("ix_article_translations_article_id", "article_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[str] = mapped_column(String(36), nullable=False)
    sentence_index: Mapped[int] = mapped_column(Integer, nullable=False)
    word_index: Mapped[int] = mapped_column(Integer, nullable=False)
    word: Mapped[str] = mapped_column(String(100), nullable=False)
    lemma: Mapped[str] = mapped_column(String(100), nullable=False)
    translation: Mapped[str] = mapped_column(Text, nullable=False)
