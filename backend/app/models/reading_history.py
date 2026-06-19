from datetime import datetime
from uuid import uuid4

from sqlalchemy import String, DateTime, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserReadingHistory(Base):
    __tablename__ = "user_reading_history"
    __table_args__ = (UniqueConstraint("user_id", "article_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    article_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    last_read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    book_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    last_sentence_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
