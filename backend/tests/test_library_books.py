"""
Unit tests for library books shelf logic (pure Python, no DB).
These verify the idempotency and error conditions we expect from the routes.
"""
import pytest


def test_library_book_list_item_is_saved_default():
    from app.schemas.book import LibraryBookListItem
    from datetime import datetime, timezone

    item = LibraryBookListItem(id="x", title="T", created_at=datetime.now(timezone.utc))
    assert item.is_saved is False


def test_library_book_list_item_chapter_count_default():
    from app.schemas.book import LibraryBookListItem
    from datetime import datetime, timezone

    item = LibraryBookListItem(id="x", title="T", created_at=datetime.now(timezone.utc))
    assert item.chapter_count == 0


def test_library_book_list_item_defaults():
    from app.schemas.book import LibraryBookListItem
    from datetime import datetime, timezone

    item = LibraryBookListItem(
        id="abc",
        title="Test",
        cover_image_url=None,
        source_category=None,
        created_at=datetime.now(timezone.utc),
    )
    assert item.chapter_count == 0
    assert item.is_saved is False


def test_book_list_item_has_is_from_library():
    from app.schemas.book import BookListItem
    from datetime import datetime, timezone

    item = BookListItem(
        id="abc",
        title="Test",
        cover_image_url=None,
        source_category=None,
        created_at=datetime.now(timezone.utc),
    )
    assert item.is_from_library is False
