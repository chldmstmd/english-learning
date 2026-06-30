from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete as sa_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.article import Article
from app.models.paragraph import ArticleParagraph
from app.models.reading_history import UserReadingHistory
from app.models.user import User
from app.schemas.article import (
    ArticleCreateRequest,
    ArticleDetailResponse,
    ArticleListItem,
    ArticleParagraphSchema,
    ArticleTranslateResponse,
    ArticleUpdateRequest,
    ProgressUpdateRequest,
)
from app.services import annotation_service, batch_translation_service, paragraph_service

router = APIRouter(tags=["articles"])


async def _article_detail_response(
    db: AsyncSession,
    article: Article,
    current_user: User,
) -> ArticleDetailResponse:
    history = await db.scalar(
        select(UserReadingHistory).where(
            UserReadingHistory.user_id == current_user.id,
            UserReadingHistory.article_id == article.id,
        )
    )
    paragraph_rows = await paragraph_service.get_article_paragraphs(db, article.id)
    annotations = await annotation_service.get_article_annotations(db, article.id, current_user.id)
    return ArticleDetailResponse(
        id=article.id,
        title=article.title,
        raw_text=article.raw_text,
        tokens=article.tokens,
        sentences=article.sentences,
        paragraphs=[
            ArticleParagraphSchema(
                id=link.id,
                paragraph_version_id=version.id,
                position=link.position,
                raw_text=version.raw_text,
                tokens=version.tokens,
                sentences=version.sentences,
                word_count=version.word_count,
            )
            for link, version in paragraph_rows
        ],
        word_count=article.word_count,
        annotations=annotations,
        translation_status=article.translation_status,
        translation_progress=article.translation_progress,
        last_sentence_index=history.last_sentence_index if history else None,
    )


@router.post("/articles", response_model=ArticleListItem, status_code=201)
async def create_article(
    body: ArticleCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    paragraphs = paragraph_service.split_paragraphs(body.raw_text)
    if not paragraphs:
        raise HTTPException(status_code=400, detail="Article text is empty")
    normalized_text = paragraph_service.normalize_article_text(paragraphs)

    if sum(len(paragraph.split()) for paragraph in paragraphs) > 10000:
        raise HTTPException(status_code=400, detail="Article exceeds 10,000 word limit")

    article = Article(
        user_id=current_user.id,
        title=body.title,
        raw_text=normalized_text,
        tokens=[],
        sentences=[],
        word_count=0,
    )
    db.add(article)
    await db.flush()
    await paragraph_service.replace_article_paragraphs(db, article, body.raw_text)

    await db.commit()
    return ArticleListItem.model_validate(article)


@router.put("/articles/{article_id}/progress", status_code=200)
async def update_progress(
    article_id: str,
    body: ProgressUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    article = await db.scalar(
        select(Article).where(Article.id == article_id, Article.user_id == current_user.id)
    )
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
        existing.last_read_at = datetime.now(timezone.utc)
    else:
        db.add(UserReadingHistory(
            user_id=current_user.id,
            article_id=article_id,
            last_sentence_index=body.last_sentence_index,
        ))
    await db.commit()
    return {"saved": True}


@router.get("/articles", response_model=list[ArticleListItem])
async def list_articles(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns the user's private article containers, newest first."""
    return list(await db.scalars(
        select(Article)
        .where(Article.user_id == current_user.id)
        .order_by(Article.created_at.desc())
    ))


@router.get("/articles/{article_id}", response_model=ArticleDetailResponse)
async def get_article(
    article_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    article = await db.scalar(
        select(Article).where(Article.id == article_id, Article.user_id == current_user.id)
    )
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    return await _article_detail_response(db, article, current_user)


@router.get("/articles/{article_id}/annotations")
async def get_article_annotations(
    article_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Polling endpoint for annotation status."""
    article = await db.scalar(
        select(Article).where(
            Article.id == article_id,
            Article.user_id == current_user.id,
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
        )
    )
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    await db.execute(sa_delete(ArticleParagraph).where(ArticleParagraph.article_id == article_id))
    await db.execute(sa_delete(UserReadingHistory).where(UserReadingHistory.article_id == article_id))
    await db.delete(article)
    await db.commit()


@router.put("/articles/{article_id}", response_model=ArticleDetailResponse, status_code=200)
async def update_article(
    article_id: str,
    body: ArticleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    article = await db.scalar(
        select(Article).where(Article.id == article_id, Article.user_id == current_user.id)
    )
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    if article.translation_status == "processing":
        raise HTTPException(status_code=409, detail="Article translation is processing")

    paragraphs = paragraph_service.split_paragraphs(body.raw_text)
    if not paragraphs:
        raise HTTPException(status_code=400, detail="Article text is empty")
    if sum(len(paragraph.split()) for paragraph in paragraphs) > 10000:
        raise HTTPException(status_code=400, detail="Article exceeds 10,000 word limit")

    article.title = body.title
    await paragraph_service.replace_article_paragraphs(db, article, body.raw_text)
    await db.commit()
    return await _article_detail_response(db, article, current_user)


@router.post("/articles/{article_id}/translate", response_model=ArticleTranslateResponse, status_code=200)
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
        return {
            "translation_status": "processing",
            "translation_progress": article.translation_progress,
        }
    if article.translation_status == "done":
        return {
            "translation_status": "done",
            "translation_progress": article.translation_progress,
        }
    progress = await batch_translation_service.prepare_translation_progress(db, article)
    batch_translation_service.spawn_translation(article_id)
    return {"translation_status": "processing", "translation_progress": progress}
