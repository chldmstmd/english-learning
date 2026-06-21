from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.vocab import VocabDetailResponse, VocabItem, VocabStatusUpdate
from app.services import dict_service, vocab_service, annotation_service

router = APIRouter(tags=["vocab"])


@router.get("/vocab", response_model=list[VocabItem])
async def get_vocab(
    status: list[str] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await vocab_service.get_user_vocab(db, current_user.id, status=status, page=page, size=size)


@router.patch("/vocab/{word}/status", response_model=VocabItem)
async def update_vocab_status(
    word: str,
    body: VocabStatusUpdate,
    force: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        vocab = await vocab_service.update_status(db, current_user.id, word, body.status, force=force)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not vocab:
        raise HTTPException(status_code=404, detail="Word not found in vocabulary")
    await db.commit()
    return vocab


@router.delete("/vocab/{word}", status_code=204)
async def delete_vocab(
    word: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    vocab = await vocab_service.get_word(db, current_user.id, word)
    if not vocab:
        raise HTTPException(status_code=404, detail="Word not found in vocabulary")
    await annotation_service.delete_word_annotations(db, current_user.id, word)
    await db.delete(vocab)
    await db.commit()


@router.get("/vocab/{word}/detail", response_model=VocabDetailResponse)
async def get_vocab_detail(
    word: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    vocab = await vocab_service.get_word(db, current_user.id, word)
    if not vocab:
        raise HTTPException(status_code=404, detail="Word not found in vocabulary")

    try:
        dict_data = await dict_service.get_word_data(word)
    except Exception:
        dict_data = {"phonetic": None, "definitions": []}

    locations = await annotation_service.get_word_click_locations(
        db, current_user.id, word, limit=3
    )

    # Lazily backfill the dictionary Chinese meaning if missing (free translation, not AI).
    if not vocab.context_translation:
        from app.services import free_translation_service
        try:
            vocab.context_translation = await free_translation_service.translate(word)
            await db.commit()
        except Exception:
            pass

    return VocabDetailResponse(
        word=vocab.word,
        phonetic=dict_data["phonetic"],
        status=vocab.status,
        context_translation=vocab.context_translation,
        source_sentence=vocab.source_sentence,
        definitions=dict_data["definitions"],
        locations=locations,
    )
