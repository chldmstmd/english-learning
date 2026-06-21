from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import select, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.article import Article
from app.models.bookmark import UserLibraryBookmark
from app.models.reading_history import UserReadingHistory
from app.models.user import User
from app.schemas.article import (
    ArticleCreateRequest,
    ArticleDetailResponse,
    ArticleListItem,
    ChapterEditRequest,
    ProgressUpdateRequest,
)
from app.services import nlp_service, vocab_service, annotation_service, batch_translation_service

router = APIRouter(tags=["articles"])


@router.post("/articles", response_model=ArticleListItem, status_code=201)
async def create_article(
    body: ArticleCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
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
    )
    db.add(article)
    await db.flush()

    await db.commit()
    return ArticleListItem.model_validate(article)


@router.put("/articles/{article_id}", response_model=ArticleListItem)
async def edit_article(
    article_id: str,
    body: ChapterEditRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    article = await db.scalar(
        select(Article).where(Article.id == article_id, Article.user_id == current_user.id)
    )
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    old_sentence_count = len(article.sentences)
    tokens, sentences, word_count = nlp_service.tokenize(body.raw_text)
    if word_count > 10000:
        raise HTTPException(status_code=400, detail="Article exceeds 10,000 word limit")

    article.title = body.title
    article.raw_text = body.raw_text
    article.tokens = tokens
    article.sentences = sentences
    article.word_count = word_count
    article.translation_status = "stale"

    # Position annotations may now point at different words -> mark mismatches stale.
    await annotation_service.revalidate_article_annotations(db, article_id, tokens)

    # If sentence count changed, the saved resume anchor is no longer valid -> reset to chapter start
    if len(sentences) != old_sentence_count:
        await db.execute(
            update(UserReadingHistory)
            .where(UserReadingHistory.article_id == article_id)
            .values(last_sentence_index=0)
        )

    await db.commit()
    return ArticleListItem.model_validate(article)


@router.put("/articles/{article_id}/progress", status_code=200)
async def update_progress(
    article_id: str,
    body: ProgressUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    article = await db.scalar(select(Article).where(Article.id == article_id))
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    existing = await db.scalar(
        select(UserReadingHistory).where(
            UserReadingHistory.user_id == current_user.id,
            UserReadingHistory.article_id == article_id,
        )
    )
    if existing:
        existing.last_sentence_index = body.last_sentence_index
        existing.book_id = article.book_id
        existing.last_read_at = datetime.now(timezone.utc)
    else:
        db.add(UserReadingHistory(
            user_id=current_user.id,
            article_id=article_id,
            book_id=article.book_id,
            last_sentence_index=body.last_sentence_index,
        ))
    await db.commit()
    return {"saved": True}


@router.get("/articles", response_model=list[ArticleListItem])
async def list_articles(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns user's own articles + bookmarked library articles, newest first."""
    # User's own standalone uploads (book chapters are excluded; they live inside their book)
    own = list(await db.scalars(
        select(Article)
        .where(
            Article.user_id == current_user.id,
            Article.is_library == False,  # noqa: E712
            Article.book_id == None,  # noqa: E711
        )
        .order_by(Article.created_at.desc())
    ))

    # Bookmarked library articles (sorted by bookmark time)
    bookmarks = list(await db.scalars(
        select(UserLibraryBookmark)
        .where(UserLibraryBookmark.user_id == current_user.id)
        .order_by(UserLibraryBookmark.created_at.desc())
    ))
    bookmark_article_ids = [b.article_id for b in bookmarks]
    bookmark_times = {b.article_id: b.created_at for b in bookmarks}

    bookmarked_articles: list[Article] = []
    if bookmark_article_ids:
        rows = list(await db.scalars(
            select(Article).where(Article.id.in_(bookmark_article_ids))
        ))
        bookmarked_articles = sorted(rows, key=lambda a: bookmark_times[a.id], reverse=True)

    result = []
    for a in own:
        result.append(ArticleListItem.model_validate(a))
    for a in bookmarked_articles:
        item = ArticleListItem.model_validate(a)
        item.created_at = bookmark_times[a.id]  # show bookmark time in list
        result.append(item)

    return result


@router.get("/articles/{article_id}", response_model=ArticleDetailResponse)
async def get_article(
    article_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    article = await db.scalar(
        select(Article).where(Article.id == article_id, Article.user_id == current_user.id)
    )
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    prev_article_id = None
    next_article_id = None
    if article.book_id is not None and article.chapter_order is not None:
        prev_article_id = await db.scalar(
            select(Article.id)
            .where(Article.book_id == article.book_id, Article.chapter_order < article.chapter_order)
            .order_by(Article.chapter_order.desc())
            .limit(1)
        )
        next_article_id = await db.scalar(
            select(Article.id)
            .where(Article.book_id == article.book_id, Article.chapter_order > article.chapter_order)
            .order_by(Article.chapter_order.asc())
            .limit(1)
        )

    history = await db.scalar(
        select(UserReadingHistory).where(
            UserReadingHistory.user_id == current_user.id,
            UserReadingHistory.article_id == article_id,
        )
    )
    last_sentence_index = history.last_sentence_index if history else None

    annotations = await annotation_service.get_article_annotations(db, article_id, current_user.id)
    word_statuses = await vocab_service.get_all_word_statuses(db, current_user.id)

    article_lemmas = {t["lemma"] for t in article.tokens if t["is_alpha"]}
    article_word_statuses = {w: s for w, s in word_statuses.items() if w in article_lemmas}

    return ArticleDetailResponse(
        id=article.id,
        title=article.title,
        tokens=article.tokens,
        sentences=article.sentences,
        word_count=article.word_count,
        annotations=annotations,
        word_statuses=article_word_statuses,
        translation_status=article.translation_status,
        book_id=article.book_id,
        chapter_order=article.chapter_order,
        prev_article_id=prev_article_id,
        next_article_id=next_article_id,
        last_sentence_index=last_sentence_index,
    )


@router.get("/articles/{article_id}/annotations")
async def get_article_annotations(
    article_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Polling endpoint for annotation status (user articles and library articles)."""
    article = await db.scalar(
        select(Article).where(
            Article.id == article_id,
            or_(Article.user_id == current_user.id, Article.is_library == True),  # noqa: E712
        )
    )
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return await annotation_service.get_article_annotations(db, article_id, current_user.id)


@router.delete("/articles/{article_id}", status_code=204)
async def delete_article(
    article_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    article = await db.scalar(
        select(Article).where(
            Article.id == article_id,
            Article.user_id == current_user.id,
            Article.is_library == False,  # noqa: E712
        )
    )
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    await db.delete(article)
    await db.commit()


@router.post("/articles/{article_id}/translate", status_code=200)
async def translate_article(
    article_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    article = await db.scalar(
        select(Article).where(Article.id == article_id, Article.user_id == current_user.id)
    )
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    if article.translation_status == "processing":
        return {"translation_status": "processing"}
    article.translation_status = "processing"
    await db.commit()
    batch_translation_service.spawn_translation(article_id)
    return {"translation_status": "processing"}
