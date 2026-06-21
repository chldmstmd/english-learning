from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_content_admin
from app.models.annotation import ArticleAnnotation
from app.models.article import Article
from app.models.article_translation import ArticleTranslation
from app.models.book import Book
from app.models.bookmark import UserLibraryBookmark
from app.models.reading_history import UserReadingHistory
from app.models.user import User
from app.schemas.article import (
    AdminArticleCreateRequest,
    AdminArticlePatchRequest,
    ArticleListItem,
    LibraryArticleListItem,
)
from app.schemas.book import BookCreateRequest, BookPatchRequest, ChapterCreateRequest, ChapterPatchRequest, LibraryBookListItem
from app.services import annotation_service, batch_translation_service, nlp_service

router = APIRouter(prefix="/admin", tags=["admin"])


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
    if body.raw_text is not None:
        tokens, sentences, word_count = nlp_service.tokenize(body.raw_text)
        if word_count > 10000:
            raise HTTPException(status_code=400, detail="Article exceeds 10,000 word limit")
        article.raw_text = body.raw_text
        article.tokens = tokens
        article.sentences = sentences
        article.word_count = word_count
        article.translation_status = "stale"
        await db.execute(sa_delete(ArticleTranslation).where(ArticleTranslation.article_id == article_id))
        # Library articles are shared across users; re-tokenizing shifts token
        # positions, so mark every user's position annotations stale on mismatch.
        await annotation_service.revalidate_article_annotations(db, article_id, tokens)
    if body.difficulty is not None:
        article.difficulty = body.difficulty
    if body.source_category is not None:
        article.source_category = body.source_category

    await db.commit()
    return LibraryArticleListItem.model_validate(article)


@router.post("/library/articles/{article_id}/translate", status_code=200)
async def translate_library_article(
    article_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_content_admin),
):
    article = await db.scalar(
        select(Article).where(Article.id == article_id, Article.is_library == True)  # noqa: E712
    )
    if not article:
        raise HTTPException(status_code=404, detail="Library article not found")
    if article.translation_status == "processing":
        return {"translation_status": "processing"}
    article.translation_status = "processing"
    await db.commit()
    batch_translation_service.spawn_translation(article_id)
    return {"translation_status": "processing"}


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


@router.patch("/library/books/{book_id}", response_model=LibraryBookListItem)
async def update_library_book(
    book_id: str,
    body: BookPatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_content_admin),
):
    book = await db.scalar(
        select(Book).where(Book.id == book_id, Book.is_library == True)  # noqa: E712
    )
    if not book:
        raise HTTPException(status_code=404, detail="Library book not found")

    if body.title is not None:
        book.title = body.title
    if body.cover_image_url is not None:
        book.cover_image_url = body.cover_image_url
    if body.source_category is not None:
        book.source_category = body.source_category

    await db.commit()

    chapter_count = await db.scalar(
        select(func.count(Article.id)).where(Article.book_id == book_id)
    )
    item = LibraryBookListItem.model_validate(book)
    item.chapter_count = chapter_count or 0
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

    chapter_ids = list(await db.scalars(
        select(Article.id).where(Article.book_id == book_id)
    ))
    if chapter_ids:
        await db.execute(sa_delete(ArticleAnnotation).where(ArticleAnnotation.article_id.in_(chapter_ids)))
        await db.execute(sa_delete(UserReadingHistory).where(UserReadingHistory.article_id.in_(chapter_ids)))
        await db.execute(sa_delete(UserLibraryBookmark).where(UserLibraryBookmark.article_id.in_(chapter_ids)))
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
    return ArticleListItem.model_validate(article)


@router.patch("/library/books/{book_id}/chapters/{chapter_id}", response_model=ArticleListItem)
async def update_library_chapter(
    book_id: str,
    chapter_id: str,
    body: ChapterPatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_content_admin),
):
    article = await db.scalar(
        select(Article).where(Article.id == chapter_id, Article.book_id == book_id)
    )
    if not article:
        raise HTTPException(status_code=404, detail="Chapter not found")
    if body.title is not None:
        article.title = body.title
    if body.raw_text is not None:
        tokens, sentences, word_count = nlp_service.tokenize(body.raw_text)
        if word_count > 10000:
            raise HTTPException(status_code=400, detail="Chapter exceeds 10,000 word limit")
        article.raw_text = body.raw_text
        article.tokens = tokens
        article.sentences = sentences
        article.word_count = word_count
        article.translation_status = "stale"
        await db.execute(sa_delete(ArticleTranslation).where(ArticleTranslation.article_id == chapter_id))
        # Library chapters are shared across users; re-tokenizing shifts token
        # positions, so mark every user's position annotations stale on mismatch.
        await annotation_service.revalidate_article_annotations(db, chapter_id, tokens)
    await db.commit()
    return ArticleListItem.model_validate(article)


@router.post("/library/books/{book_id}/chapters/{chapter_id}/translate", status_code=200)
async def translate_library_chapter(
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
    if article.translation_status == "processing":
        return {"translation_status": "processing"}
    article.translation_status = "processing"
    await db.commit()
    batch_translation_service.spawn_translation(chapter_id)
    return {"translation_status": "processing"}


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

    await db.execute(sa_delete(ArticleAnnotation).where(ArticleAnnotation.article_id == chapter_id))
    await db.execute(sa_delete(UserReadingHistory).where(UserReadingHistory.article_id == chapter_id))
    await db.execute(sa_delete(UserLibraryBookmark).where(UserLibraryBookmark.article_id == chapter_id))
    await db.delete(article)
    await db.commit()
