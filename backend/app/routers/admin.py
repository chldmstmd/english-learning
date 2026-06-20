import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_content_admin
from app.models.annotation import ArticleAnnotation
from app.models.article import Article
from app.models.book import Book
from app.models.bookmark import UserLibraryBookmark
from app.models.reading_history import UserReadingHistory
from app.models.sync_log import VoaSyncLog
from app.models.user import User
from app.schemas.article import (
    AdminArticleCreateRequest,
    AdminArticlePatchRequest,
    ArticleListItem,
    LibraryArticleListItem,
)
from app.schemas.book import BookCreateRequest, ChapterCreateRequest, LibraryBookListItem
from app.services import batch_translation_service, nlp_service, voa_service

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/sync-voa", summary="Manually trigger VOA RSS sync")
async def sync_voa(
    current_user: User = Depends(require_content_admin),
):
    """Immediately triggers a full VOA feed sync. May take up to a few minutes."""
    results = await voa_service.sync_all_feeds()
    total_new = sum(r["new_articles"] for r in results)
    return {"results": results, "total_new_articles": total_new}


@router.get("/sync-voa/logs", summary="View VOA sync history")
async def get_sync_logs(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_content_admin),
):
    rows = list(await db.scalars(
        select(VoaSyncLog).order_by(VoaSyncLog.synced_at.desc()).limit(limit)
    ))
    return [
        {
            "id": r.id,
            "feed_url": r.feed_url,
            "synced_at": r.synced_at,
            "new_articles": r.new_articles,
            "status": r.status,
            "error_message": r.error_message,
        }
        for r in rows
    ]


@router.post("/library/articles", response_model=LibraryArticleListItem, status_code=201)
async def create_library_article(
    body: AdminArticleCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_content_admin),
):
    tokens, sentences, word_count = nlp_service.tokenize(body.raw_text)
    if word_count > 10000:
        raise HTTPException(status_code=400, detail="Article exceeds 10,000 word limit")

    article = Article(
        user_id=current_user.id,
        title=body.title,
        raw_text=body.raw_text,
        tokens=tokens,
        sentences=sentences,
        word_count=word_count,
        is_library=True,
        difficulty=body.difficulty,
        source_category=body.source_category,
    )
    db.add(article)
    await db.commit()
    asyncio.create_task(batch_translation_service.translate_article(article.id))
    return LibraryArticleListItem.model_validate(article)


@router.patch("/library/articles/{article_id}", response_model=LibraryArticleListItem)
async def update_library_article(
    article_id: str,
    body: AdminArticlePatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_content_admin),
):
    article = await db.scalar(
        select(Article).where(Article.id == article_id, Article.is_library == True)  # noqa: E712
    )
    if not article:
        raise HTTPException(status_code=404, detail="Library article not found")

    if body.title is not None:
        article.title = body.title
    if body.difficulty is not None:
        article.difficulty = body.difficulty
    if body.source_category is not None:
        article.source_category = body.source_category

    await db.commit()
    return LibraryArticleListItem.model_validate(article)


@router.delete("/library/articles/{article_id}", status_code=204)
async def delete_library_article(
    article_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_content_admin),
):
    article = await db.scalar(
        select(Article).where(Article.id == article_id, Article.is_library == True)  # noqa: E712
    )
    if not article:
        raise HTTPException(status_code=404, detail="Library article not found")

    await db.execute(sa_delete(ArticleAnnotation).where(ArticleAnnotation.article_id == article_id))
    await db.execute(sa_delete(UserReadingHistory).where(UserReadingHistory.article_id == article_id))
    await db.execute(sa_delete(UserLibraryBookmark).where(UserLibraryBookmark.article_id == article_id))
    await db.delete(article)
    await db.commit()


@router.post("/library/books", response_model=LibraryBookListItem, status_code=201)
async def create_library_book(
    body: BookCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_content_admin),
):
    book = Book(
        user_id=current_user.id,
        title=body.title,
        cover_image_url=body.cover_image_url,
        source_category=body.source_category,
        is_library=True,
    )
    db.add(book)
    await db.commit()
    item = LibraryBookListItem.model_validate(book)
    item.chapter_count = 0
    return item


@router.delete("/library/books/{book_id}", status_code=204)
async def delete_library_book(
    book_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_content_admin),
):
    book = await db.scalar(
        select(Book).where(Book.id == book_id, Book.is_library == True)  # noqa: E712
    )
    if not book:
        raise HTTPException(status_code=404, detail="Library book not found")

    await db.execute(sa_delete(Article).where(Article.book_id == book_id))
    await db.delete(book)
    await db.commit()


@router.post("/library/books/{book_id}/chapters", response_model=ArticleListItem, status_code=201)
async def add_library_chapter(
    book_id: str,
    body: ChapterCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_content_admin),
):
    book = await db.scalar(
        select(Book).where(Book.id == book_id, Book.is_library == True)  # noqa: E712
    )
    if not book:
        raise HTTPException(status_code=404, detail="Library book not found")

    tokens, sentences, word_count = nlp_service.tokenize(body.raw_text)
    if word_count > 10000:
        raise HTTPException(status_code=400, detail="Chapter exceeds 10,000 word limit")

    max_order = await db.scalar(
        select(func.max(Article.chapter_order)).where(Article.book_id == book_id)
    )
    next_order = (max_order or 0) + 1

    article = Article(
        user_id=current_user.id,
        title=body.title,
        raw_text=body.raw_text,
        tokens=tokens,
        sentences=sentences,
        word_count=word_count,
        book_id=book_id,
        chapter_order=next_order,
    )
    db.add(article)
    await db.commit()
    asyncio.create_task(batch_translation_service.translate_article(article.id))
    return ArticleListItem.model_validate(article)


@router.delete("/library/books/{book_id}/chapters/{chapter_id}", status_code=204)
async def delete_library_chapter(
    book_id: str,
    chapter_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_content_admin),
):
    article = await db.scalar(
        select(Article).where(Article.id == chapter_id, Article.book_id == book_id)
    )
    if not article:
        raise HTTPException(status_code=404, detail="Chapter not found")

    await db.delete(article)
    await db.commit()
