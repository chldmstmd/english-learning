import asyncio

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.article import Article
from app.models.bookmark import UserLibraryBookmark
from app.models.user import User
from app.schemas.article import ArticleCreateRequest, ArticleDetailResponse, ArticleListItem
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


@router.get("/articles", response_model=list[ArticleListItem])
async def list_articles(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns user's own articles + bookmarked library articles, newest first."""
    # User's own uploads
    own = list(await db.scalars(
        select(Article)
        .where(Article.user_id == current_user.id, Article.is_library == False)  # noqa: E712
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

    annotations = await annotation_service.get_article_annotations(db, article_id, current_user.id)
    word_statuses = await vocab_service.get_all_word_statuses(db, current_user.id)

    article_lemmas = {t["lemma"] for t in article.tokens if t["is_alpha"]}
    article_word_statuses = {w: s for w, s in word_statuses.items() if w in article_lemmas}

    has_pending = any(a["gen_status"] == "pending" for a in annotations.values())
    if has_pending:
        background_tasks.add_task(
            annotation_service.generate_pending_translations_task, article_id, current_user.id
        )

    return ArticleDetailResponse(
        id=article.id,
        title=article.title,
        tokens=article.tokens,
        sentences=article.sentences,
        word_count=article.word_count,
        annotations=annotations,
        word_statuses=article_word_statuses,
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
        select(Article).where(Article.id == article_id, Article.user_id == current_user.id)
    )
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    await db.delete(article)
    await db.commit()
