from __future__ import annotations

import hashlib
import re
from collections import defaultdict, deque
from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.article import Article
from app.models.paragraph import ArticleParagraph, ParagraphTranslation, ParagraphVersion
from app.services import nlp_service


def split_paragraphs(raw_text: str) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", raw_text.strip()) if part.strip()]
    return paragraphs


def normalize_article_text(paragraphs: Iterable[str]) -> str:
    return "\n\n".join(paragraphs)


def _text_hash(raw_text: str) -> str:
    return hashlib.sha256(raw_text.encode("utf-8")).hexdigest()


async def get_or_create_paragraph_version(db: AsyncSession, raw_text: str) -> ParagraphVersion:
    text_hash = _text_hash(raw_text)
    existing = await db.scalar(
        select(ParagraphVersion).where(
            ParagraphVersion.text_hash == text_hash,
            ParagraphVersion.raw_text == raw_text,
        )
    )
    if existing:
        return existing

    tokens, sentences, word_count = nlp_service.tokenize(raw_text)
    version = ParagraphVersion(
        raw_text=raw_text,
        tokens=tokens,
        sentences=sentences,
        word_count=word_count,
        text_hash=text_hash,
    )
    db.add(version)
    await db.flush()
    return version


def _apply_article_snapshot(article: Article, paragraphs: list[str]) -> None:
    raw_text = normalize_article_text(paragraphs)
    tokens, sentences, word_count = nlp_service.tokenize(raw_text)
    article.raw_text = raw_text
    article.tokens = tokens
    article.sentences = sentences
    article.word_count = word_count


async def replace_article_paragraphs(
    db: AsyncSession,
    article: Article,
    raw_text: str,
) -> list[ArticleParagraph]:
    paragraphs = split_paragraphs(raw_text)
    _apply_article_snapshot(article, paragraphs)

    old_rows = await get_article_paragraphs(db, article.id)
    old_versions_by_text: dict[str, deque[ParagraphVersion]] = defaultdict(deque)
    for _, version in old_rows:
        old_versions_by_text[version.raw_text].append(version)

    versions: list[ParagraphVersion] = []
    for paragraph in paragraphs:
        if old_versions_by_text[paragraph]:
            versions.append(old_versions_by_text[paragraph].popleft())
        else:
            versions.append(await get_or_create_paragraph_version(db, paragraph))

    old_links = [link for link, _ in old_rows]
    available: dict[str, deque[ArticleParagraph]] = defaultdict(deque)
    for index, link in enumerate(old_links):
        link.position = -(index + 1)
        available[link.paragraph_version_id].append(link)
    await db.flush()

    used_link_ids: set[str] = set()
    new_links: list[ArticleParagraph] = []
    for position, version in enumerate(versions):
        if available[version.id]:
            link = available[version.id].popleft()
            link.position = position
        else:
            link = ArticleParagraph(
                article_id=article.id,
                paragraph_version_id=version.id,
                position=position,
            )
            db.add(link)
        await db.flush()
        used_link_ids.add(link.id)
        new_links.append(link)

    for link in old_links:
        if link.id not in used_link_ids:
            await db.delete(link)

    await db.flush()
    await recalculate_translation_progress(db, article)
    return new_links


async def get_article_paragraphs(
    db: AsyncSession,
    article_id: str,
) -> list[tuple[ArticleParagraph, ParagraphVersion]]:
    rows = await db.execute(
        select(ArticleParagraph, ParagraphVersion)
        .join(ParagraphVersion, ArticleParagraph.paragraph_version_id == ParagraphVersion.id)
        .where(ArticleParagraph.article_id == article_id)
        .order_by(ArticleParagraph.position)
    )
    return list(rows.all())


async def recalculate_translation_progress(db: AsyncSession, article: Article) -> dict:
    rows = await get_article_paragraphs(db, article.id)
    version_ids = {version.id for _, version in rows}
    translated_keys: set[tuple[str, int, int]] = set()
    if version_ids:
        translation_rows = await db.execute(
            select(
                ParagraphTranslation.paragraph_version_id,
                ParagraphTranslation.sentence_index,
                ParagraphTranslation.word_index,
            ).where(ParagraphTranslation.paragraph_version_id.in_(version_ids))
        )
        translated_keys = {
            (str(version_id), int(sentence_index), int(word_index))
            for version_id, sentence_index, word_index in translation_rows
        }

    total_words = 0
    processed_words = 0
    completed_chunks = 0
    total_chunks = 0
    for _, version in rows:
        paragraph_keys: list[tuple[str, int, int]] = []
        for token in version.tokens:
            if token.get("is_alpha"):
                key = (
                    version.id,
                    int(token["sentence_index"]),
                    int(token["index"]),
                )
                total_words += 1
                paragraph_keys.append(key)
                if key in translated_keys:
                    processed_words += 1
        if paragraph_keys:
            total_chunks += 1
            if all(key in translated_keys for key in paragraph_keys):
                completed_chunks += 1

    if total_words == 0:
        status = "done"
    elif processed_words == 0:
        status = "untranslated"
    elif processed_words == total_words:
        status = "done"
    else:
        status = "stale"

    article.translation_total_words = total_words
    article.translation_processed_words = processed_words
    article.translation_total_chunks = total_chunks
    article.translation_completed_chunks = completed_chunks
    article.translation_status = status
    await db.flush()
    return article.translation_progress


async def delete_article_paragraph_links(db: AsyncSession, article_id: str) -> None:
    await db.execute(delete(ArticleParagraph).where(ArticleParagraph.article_id == article_id))
