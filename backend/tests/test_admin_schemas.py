import pytest
from pydantic import ValidationError


def test_admin_article_create_requires_title():
    from app.schemas.article import AdminArticleCreateRequest
    with pytest.raises(ValidationError):
        AdminArticleCreateRequest(raw_text="some text")


def test_admin_article_create_requires_raw_text():
    from app.schemas.article import AdminArticleCreateRequest
    with pytest.raises(ValidationError):
        AdminArticleCreateRequest(title="My Article")


def test_admin_article_create_valid():
    from app.schemas.article import AdminArticleCreateRequest
    req = AdminArticleCreateRequest(title="T", raw_text="some text")
    assert req.difficulty is None
    assert req.source_category is None


def test_admin_article_patch_all_none():
    from app.schemas.article import AdminArticlePatchRequest
    req = AdminArticlePatchRequest()
    assert req.title is None
    assert req.difficulty is None
    assert req.source_category is None
