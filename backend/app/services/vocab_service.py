from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vocabulary import Vocabulary

VALID_TRANSITIONS: dict[str, list[str]] = {
    "new": ["reviewing"],
    "reviewing": ["mastered"],
    "mastered": ["new"],
}


async def get_user_vocab(
    db: AsyncSession,
    user_id: str,
    status: list[str] | None = None,
    page: int = 1,
    size: int = 50,
) -> list[Vocabulary]:
    stmt = select(Vocabulary).where(Vocabulary.user_id == user_id)
    if status:
        stmt = stmt.where(Vocabulary.status.in_(status))
    stmt = stmt.order_by(Vocabulary.updated_at.desc()).offset((page - 1) * size).limit(size)
    return list(await db.scalars(stmt))


async def get_word(db: AsyncSession, user_id: str, word: str) -> Vocabulary | None:
    return await db.scalar(
        select(Vocabulary).where(Vocabulary.user_id == user_id, Vocabulary.word == word)
    )


async def get_all_word_statuses(db: AsyncSession, user_id: str) -> dict[str, str]:
    """Return {word: status} for all vocabulary entries."""
    result = await db.execute(
        select(Vocabulary.word, Vocabulary.status).where(Vocabulary.user_id == user_id)
    )
    return {row.word: row.status for row in result}


async def upsert_word(
    db: AsyncSession,
    user_id: str,
    word: str,
    pos: str | None = None,
    context_translation: str | None = None,
    source_sentence: str | None = None,
) -> Vocabulary:
    """
    Create a new vocab entry (status=new) or handle mastered→new re-entry.
    If word already exists with status new/reviewing, return as-is.
    """
    existing = await get_word(db, user_id, word)
    if existing:
        if existing.status == "mastered":
            # Re-entry: mastered → new
            existing.status = "new"
            existing.context_translation = context_translation or existing.context_translation
            existing.source_sentence = source_sentence or existing.source_sentence
            existing.updated_at = datetime.now(timezone.utc)
        await db.flush()
        return existing

    vocab = Vocabulary(
        user_id=user_id,
        word=word,
        pos=pos,
        context_translation=context_translation,
        source_sentence=source_sentence,
        status="new",
    )
    db.add(vocab)
    await db.flush()
    return vocab


async def update_status(
    db: AsyncSession,
    user_id: str,
    word: str,
    new_status: str,
    force: bool = False,
) -> Vocabulary | None:
    vocab = await get_word(db, user_id, word)
    if not vocab:
        return None

    if not force:
        allowed = VALID_TRANSITIONS.get(vocab.status, [])
        if new_status not in allowed:
            raise ValueError(f"Invalid transition: {vocab.status} → {new_status}")

    vocab.status = new_status
    vocab.updated_at = datetime.now(timezone.utc)
    if new_status == "mastered":
        vocab.mastered_at = datetime.now(timezone.utc)
    elif new_status != "mastered":
        vocab.mastered_at = None

    await db.flush()
    return vocab


async def update_context_translation(
    db: AsyncSession,
    user_id: str,
    word: str,
    translation: str,
) -> None:
    vocab = await get_word(db, user_id, word)
    if vocab:
        vocab.context_translation = translation
        await db.flush()
