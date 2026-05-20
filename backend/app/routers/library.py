from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy import select, nulls_last
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.article import Article
from app.models.bookmark import UserLibraryBookmark
from app.models.reading_history import UserReadingHistory
from app.models.user import User
from app.schemas.article import ArticleDetailResponse, LibraryArticleListItem
from app.services import annotation_service, vocab_service

router = APIRouter(tags=["library"])


@router.get("/library", response_model=list[LibraryArticleListItem])
async def list_library_articles(
    category: str | None = Query(None),
    difficulty: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = select(Article).where(Article.is_library == True)  # noqa: E712
    if category:
        stmt = stmt.where(Article.source_category == category)
    if difficulty:
        stmt = stmt.where(Article.difficulty == difficulty)
    stmt = stmt.order_by(nulls_last(Article.published_at.desc()), Article.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    articles = list(await db.scalars(stmt))

    if not articles:
        return []

    article_ids = [a.id for a in articles]

    # Fetch bookmark status for current user
    bookmarked_ids = set(await db.scalars(
        select(UserLibraryBookmark.article_id).where(
            UserLibraryBookmark.user_id == current_user.id,
            UserLibraryBookmark.article_id.in_(article_ids),
        )
    ))

    # Fetch reading history for current user
    read_rows = list(await db.scalars(
        select(UserReadingHistory).where(
            UserReadingHistory.user_id == current_user.id,
            UserReadingHistory.article_id.in_(article_ids),
        )
    ))
    read_at_map = {r.article_id: r.last_read_at for r in read_rows}

    result = []
    for a in articles:
        item = LibraryArticleListItem.model_validate(a)
        item.is_bookmarked = a.id in bookmarked_ids
        item.read_at = read_at_map.get(a.id)
        result.append(item)
    return result


@router.get("/library/{article_id}", response_model=ArticleDetailResponse)
async def get_library_article(
    article_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    article = await db.scalar(
        select(Article).where(Article.id == article_id, Article.is_library == True)  # noqa: E712
    )
    if not article:
        raise HTTPException(status_code=404, detail="Library article not found")

    # Record reading history (upsert)
    existing_history = await db.scalar(
        select(UserReadingHistory).where(
            UserReadingHistory.user_id == current_user.id,
            UserReadingHistory.article_id == article_id,
        )
    )
    if existing_history:
        from datetime import datetime, timezone
        existing_history.last_read_at = datetime.now(timezone.utc)
    else:
        db.add(UserReadingHistory(user_id=current_user.id, article_id=article_id))

    # Lazy annotation sync: for vocab words in this article without an annotation yet,
    # create pending records so translations are generated on open
    existing_annotations = await annotation_service.get_article_annotations(db, article_id, current_user.id)
    word_statuses = await vocab_service.get_all_word_statuses(db, current_user.id)
    article_lemmas = {t["lemma"] for t in article.tokens if t["is_alpha"]}

    new_pending = []
    for word in word_statuses:
        if word in article_lemmas and word not in existing_annotations:
            new_pending.append(word)
            await annotation_service.upsert_annotation(
                db, article_id, current_user.id, word, gen_status="pending"
            )

    await db.commit()

    # Re-fetch annotations (now includes newly created pending ones)
    annotations = await annotation_service.get_article_annotations(db, article_id, current_user.id)
    article_word_statuses = {w: s for w, s in word_statuses.items() if w in article_lemmas}

    has_pending = any(a["gen_status"] == "pending" for a in annotations.values())
    if has_pending:
        background_tasks.add_task(
            annotation_service.generate_pending_translations_task, article_id, current_user.id
        )

    # Bookmark status
    is_bookmarked = bool(await db.scalar(
        select(UserLibraryBookmark).where(
            UserLibraryBookmark.user_id == current_user.id,
            UserLibraryBookmark.article_id == article_id,
        )
    ))

    return ArticleDetailResponse(
        id=article.id,
        title=article.title,
        tokens=article.tokens,
        sentences=article.sentences,
        word_count=article.word_count,
        annotations=annotations,
        word_statuses=article_word_statuses,
        is_library=True,
        is_bookmarked=is_bookmarked,
        source_url=article.source_url,
        source_category=article.source_category,
        difficulty=article.difficulty,
        published_at=article.published_at,
    )


@router.post("/library/{article_id}/bookmark", status_code=201)
async def add_bookmark(
    article_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    article = await db.scalar(
        select(Article).where(Article.id == article_id, Article.is_library == True)  # noqa: E712
    )
    if not article:
        raise HTTPException(status_code=404, detail="Library article not found")

    existing = await db.scalar(
        select(UserLibraryBookmark).where(
            UserLibraryBookmark.user_id == current_user.id,
            UserLibraryBookmark.article_id == article_id,
        )
    )
    if not existing:
        db.add(UserLibraryBookmark(user_id=current_user.id, article_id=article_id))
        await db.commit()
    return {"bookmarked": True}


@router.delete("/library/{article_id}/bookmark", status_code=200)
async def remove_bookmark(
    article_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    bookmark = await db.scalar(
        select(UserLibraryBookmark).where(
            UserLibraryBookmark.user_id == current_user.id,
            UserLibraryBookmark.article_id == article_id,
        )
    )
    if bookmark:
        await db.delete(bookmark)
        await db.commit()
    return {"bookmarked": False}
