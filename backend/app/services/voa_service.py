"""
VOA Learning English RSS sync service.

Feed URLs should be verified from learningenglish.voanews.com section pages
(look for <link rel="alternate" type="application/rss+xml"> in the page HTML).
The list below uses known patterns — update if any URL stops working.
"""
import logging
import re
import time as time_module
from datetime import datetime, timezone
from uuid import uuid4

import feedparser
import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.article import Article
from app.models.sync_log import VoaSyncLog
from app.services import nlp_service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feed configuration
# Each entry: url, category slug, difficulty ("level1" | "level2"), display label
# Verify / update these URLs from https://learningenglish.voanews.com
# ---------------------------------------------------------------------------
VOA_FEEDS: list[dict] = [
    {
        "url": "https://learningenglish.voanews.com/api/zmg_pl-vomx-tpeymtm",
        "category": "science-technology",
        "difficulty": "level2",
        "label": "Science & Technology",
    },
    {
        "url": "https://learningenglish.voanews.com/api/zmmpql-vomx-tpey-_q",
        "category": "health-lifestyle",
        "difficulty": "level2",
        "label": "Health & Lifestyle",
    },
    {
        "url": "https://learningenglish.voanews.com/api/zj_pvl-vomx-tpebb_v",
        "category": "us-history",
        "difficulty": "level1",
        "label": "US History",
    },
    {
        "url": "https://learningenglish.voanews.com/api/zmypyl-vomx-tpeyry_",
        "category": "words-stories",
        "difficulty": "level1",
        "label": "Words & Stories",
    },
]

# Number of articles to process per feed per sync run
MAX_PER_FEED = 20
# Minimum word count to accept an article (skip image-only / stub entries)
MIN_WORD_COUNT = 100


# ---------------------------------------------------------------------------
# HTML / text utilities
# ---------------------------------------------------------------------------

def _clean_html(html: str) -> str:
    """Strip HTML tags and remove VOA boilerplate footers."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "a"]):
        tag.decompose()
    text = soup.get_text(separator=" ")

    # Remove common VOA footer blocks
    text = re.sub(r"Words in This Story:.*$", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"Now it'?s your turn.*$", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"_+\s*$", "", text, flags=re.DOTALL)

    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_content(entry) -> str:
    """Get raw HTML content from a feedparser entry (usually just a teaser)."""
    if hasattr(entry, "content") and entry.content:
        return entry.content[0].value
    if hasattr(entry, "summary"):
        return entry.summary
    return ""


async def _fetch_full_article(url: str) -> str:
    """
    Fetch the full article text from a VOA article page.
    Extracts <p> tags from div.body-container (or fallback selectors).
    Returns empty string on failure.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            html = resp.text
    except Exception as exc:
        logger.warning("Failed to fetch full article %s: %s", url, exc)
        return ""

    soup = BeautifulSoup(html, "html.parser")

    # Try known VOA article body selectors in order
    body = (
        soup.select_one("div.body-container")
        or soup.select_one("div.wsw")
        or soup.select_one("article")
    )
    if not body:
        return ""

    paras = [p.get_text(" ", strip=True) for p in body.find_all("p") if p.get_text(strip=True)]
    # Skip nav/boilerplate short fragments at the start
    paras = [p for p in paras if len(p.split()) > 5]
    return "\n\n".join(paras)


def _parse_date(parsed_time) -> datetime | None:
    if parsed_time is None:
        return None
    try:
        ts = time_module.mktime(parsed_time)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except Exception:
        return None


def _extract_cover_image(entry) -> str | None:
    if hasattr(entry, "media_content"):
        for media in entry.media_content:
            if media.get("medium") == "image" or media.get("type", "").startswith("image/"):
                return media.get("url")
    if hasattr(entry, "media_thumbnail"):
        thumbs = entry.media_thumbnail
        if thumbs:
            return thumbs[0].get("url")
    return None


# ---------------------------------------------------------------------------
# Core sync logic
# ---------------------------------------------------------------------------

async def _fetch_feed_text(url: str) -> str | None:
    """Fetch RSS XML via httpx; returns raw bytes as string or None on error."""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.text
    except Exception as exc:
        logger.warning("Failed to fetch VOA feed %s: %s", url, exc)
        return None


async def sync_feed(db: AsyncSession, feed_cfg: dict) -> tuple[int, str | None]:
    """
    Sync a single VOA RSS feed.
    Returns (new_articles_count, error_message_or_None).
    """
    url = feed_cfg["url"]
    category = feed_cfg["category"]
    difficulty = feed_cfg["difficulty"]

    feed_text = await _fetch_feed_text(url)
    if feed_text is None:
        return 0, f"Failed to fetch feed: {url}"

    parsed = feedparser.parse(feed_text)
    if parsed.bozo and not parsed.entries:
        return 0, f"Feed parse error: {parsed.bozo_exception}"

    new_count = 0
    entries = parsed.entries[:MAX_PER_FEED]

    for entry in entries:
        source_url: str = getattr(entry, "link", "")
        if not source_url:
            continue

        # Dedup check
        existing = await db.scalar(
            select(Article).where(Article.source_url == source_url)
        )
        if existing:
            continue

        title: str = getattr(entry, "title", "Untitled").strip()

        # Fetch full article text from the article page (RSS only has a teaser)
        raw_text = await _fetch_full_article(source_url)
        if not raw_text:
            # Fallback to RSS summary if full page fetch fails
            raw_html = _extract_content(entry)
            raw_text = _clean_html(raw_html) if raw_html else ""
        if not raw_text:
            continue

        # Tokenize and word count check
        try:
            tokens, sentences, word_count = nlp_service.tokenize(raw_text)
        except Exception as exc:
            logger.warning("Tokenization failed for %s: %s", source_url, exc)
            continue

        if word_count < MIN_WORD_COUNT:
            logger.debug("Skipping short article (%d words): %s", word_count, title)
            continue

        published_at = _parse_date(getattr(entry, "published_parsed", None))
        cover_image_url = _extract_cover_image(entry)

        # Use a fixed system user id for library articles (no real owner)
        article = Article(
            id=str(uuid4()),
            user_id="00000000-0000-0000-0000-000000000000",  # system user
            title=title,
            raw_text=raw_text,
            tokens=tokens,
            sentences=sentences,
            word_count=word_count,
            source="voa",
            is_library=True,
            source_url=source_url,
            source_category=category,
            difficulty=difficulty,
            published_at=published_at,
            cover_image_url=cover_image_url,
        )
        try:
            db.add(article)
            await db.commit()
            new_count += 1
        except Exception as exc:
            await db.rollback()
            logger.warning("Skipping article %s: %s", source_url, exc)
            continue

    return new_count, None


async def sync_all_feeds() -> list[dict]:
    """
    Sync all configured VOA feeds.
    Each feed gets its own DB session so a failure in one doesn't affect others.
    """
    results = []
    for feed_cfg in VOA_FEEDS:
        url = feed_cfg["url"]
        logger.info("Syncing VOA feed: %s (%s)", feed_cfg["label"], url)
        # Fresh session per feed — isolates failures
        async with AsyncSessionLocal() as db:
            try:
                new_count, error = await sync_feed(db, feed_cfg)
                status = "failed" if error else "success"
                db.add(VoaSyncLog(
                    feed_url=url,
                    new_articles=new_count,
                    status=status,
                    error_message=error,
                ))
                await db.commit()
                logger.info("Feed %s: %d new, status=%s", feed_cfg["label"], new_count, status)
                results.append({"feed": url, "new_articles": new_count, "status": status, "error": error})
            except Exception as exc:
                logger.error("Unexpected error syncing feed %s: %s", url, exc)
                await db.rollback()
                try:
                    db.add(VoaSyncLog(feed_url=url, new_articles=0, status="failed", error_message=str(exc)))
                    await db.commit()
                except Exception:
                    pass
                results.append({"feed": url, "new_articles": 0, "status": "failed", "error": str(exc)})
    return results
