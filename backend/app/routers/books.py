import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete as sa_delete
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.article import Article
from app.models.book import Book
from app.models.reading_history import UserReadingHistory
from app.models.user import User
from app.models.book_shelf import UserBookShelf
from app.schemas.article import ArticleListItem
from app.schemas.book import (
    BookCreateRequest,
    BookDetailResponse,
    BookListItem,
    ChapterCreateRequest,
    ChapterListItem,
)
from app.services import nlp_service, vocab_service, annotation_service, batch_translation_service

router = APIRouter(tags=["books"])


@router.post("/books", response_model=BookListItem, status_code=201)
async def create_book(
    body: BookCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    book = Book(
        user_id=current_user.id,
        title=body.title,
        cover_image_url=body.cover_image_url,
        source_category=body.source_category,
    )
    db.add(book)
    await db.commit()
    item = BookListItem.model_validate(book)
    item.chapter_count = 0
    return item


@router.get("/books", response_model=list[BookListItem])
async def list_books(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    own_books = list(await db.scalars(
        select(Book)
        .where(Book.user_id == current_user.id, Book.is_library == False)  # noqa: E712
        .order_by(Book.created_at.desc())
    ))

    shelf_book_ids = list(await db.scalars(
        select(UserBookShelf.book_id).where(UserBookShelf.user_id == current_user.id)
    ))
    shelf_books = []
    if shelf_book_ids:
        shelf_books = list(await db.scalars(
            select(Book)
            .where(Book.id.in_(shelf_book_ids), Book.is_library == True)  # noqa: E712
            .order_by(Book.created_at.desc())
        ))

    all_books = own_books + shelf_books
    if not all_books:
        return []

    book_ids = [b.id for b in all_books]

    count_rows = await db.execute(
        select(Article.book_id, func.count(Article.id))
        .where(Article.book_id.in_(book_ids))
        .group_by(Article.book_id)
    )
    count_map = {bid: cnt for bid, cnt in count_rows.all()}

    read_rows = await db.execute(
        select(UserReadingHistory.book_id, Article.chapter_order)
        .join(Article, Article.id == UserReadingHistory.article_id)
        .where(
            UserReadingHistory.user_id == current_user.id,
            UserReadingHistory.book_id.in_(book_ids),
        )
    )
    read_map: dict[str, int] = {}
    for bid, order in read_rows.all():
        if order is not None and (bid not in read_map or order > read_map[bid]):
            read_map[bid] = order

    shelf_id_set = set(shelf_book_ids)
    result = []
    for b in all_books:
        item = BookListItem.model_validate(b)
        item.chapter_count = count_map.get(b.id, 0)
        item.read_chapter_order = read_map.get(b.id)
        item.is_from_library = b.id in shelf_id_set
        result.append(item)
    return result


@router.post("/books/{book_id}/chapters", response_model=ArticleListItem, status_code=201)
async def add_chapter(
    book_id: str,
    body: ChapterCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    book = await db.scalar(
        select(Book).where(Book.id == book_id, Book.user_id == current_user.id)
    )
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    tokens, sentences, word_count = nlp_service.tokenize(body.raw_text)
    if word_count > 10000:
        raise HTTPException(status_code=400, detail="Chapter exceeds 10,000 word limit")

    # next chapter_order = current max + 1 (1-based)
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
    await db.flush()

    word_statuses = await vocab_service.get_all_word_statuses(db, current_user.id)
    article_lemmas = {t["lemma"] for t in tokens if t["is_alpha"]}
    for word in word_statuses:
        if word in article_lemmas:
            await annotation_service.upsert_annotation(
                db, article.id, current_user.id, word, gen_status="pending"
            )

    await db.commit()
    asyncio.create_task(batch_translation_service.translate_article(article.id))
    return ArticleListItem.model_validate(article)


@router.get("/books/{book_id}", response_model=BookDetailResponse)
async def get_book(
    book_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    book = await db.scalar(select(Book).where(Book.id == book_id))
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if book.user_id != current_user.id:
        shelf_entry = await db.scalar(
            select(UserBookShelf).where(
                UserBookShelf.user_id == current_user.id,
                UserBookShelf.book_id == book_id,
            )
        )
        if not shelf_entry:
            raise HTTPException(status_code=404, detail="Book not found")

    chapters = list(await db.scalars(
        select(Article)
        .where(Article.book_id == book_id)
        .order_by(Article.chapter_order)
    ))

    # per-chapter resume positions
    history_rows = list(await db.scalars(
        select(UserReadingHistory).where(
            UserReadingHistory.user_id == current_user.id,
            UserReadingHistory.book_id == book_id,
        )
    ))
    resume_by_article = {h.article_id: h.last_sentence_index for h in history_rows}

    chapter_items = []
    for c in chapters:
        item = ChapterListItem.model_validate(c)
        item.last_sentence_index = resume_by_article.get(c.id)
        chapter_items.append(item)

    # continue-reading target = highest chapter_order the user has a history row for
    continue_article_id = None
    continue_sentence_index = None
    best_order = -1
    for c in chapters:
        if c.id in resume_by_article and (c.chapter_order or 0) > best_order:
            best_order = c.chapter_order or 0
            continue_article_id = c.id
            continue_sentence_index = resume_by_article[c.id]
    # if nothing read yet, default to first chapter
    if continue_article_id is None and chapters:
        continue_article_id = chapters[0].id
        continue_sentence_index = 0

    return BookDetailResponse(
        id=book.id,
        title=book.title,
        cover_image_url=book.cover_image_url,
        source_category=book.source_category,
        created_at=book.created_at,
        chapters=chapter_items,
        continue_article_id=continue_article_id,
        continue_sentence_index=continue_sentence_index,
    )


@router.delete("/books/{book_id}", status_code=204)
async def delete_book(
    book_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    book = await db.scalar(
        select(Book).where(Book.id == book_id, Book.user_id == current_user.id)
    )
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    # delete all chapters belonging to this book, then the book
    await db.execute(sa_delete(Article).where(Article.book_id == book_id))
    await db.delete(book)
    await db.commit()
