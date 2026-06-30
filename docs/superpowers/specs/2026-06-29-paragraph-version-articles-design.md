# Paragraph Version Articles Design

## Goal

Store articles as ordered paragraph-version references so edits can preserve pretranslation cache for unchanged paragraphs.

## Data Model

`articles` remains the article container and keeps existing status/progress fields. Paragraph content moves into immutable `paragraph_versions` rows containing `raw_text`, `tokens`, `sentences`, `word_count`, and `text_hash`.

`article_paragraphs` stores the article's ordered paragraph references:

```text
article_id + position -> paragraph_version_id
```

`paragraph_translations` replaces article-position pretranslation cache:

```text
paragraph_version_id + sentence_index + word_index -> translation
```

Clicked annotations are stored by article paragraph occurrence, so annotation state does not collide across paragraphs.

## Edit Behavior

On article edit, the backend re-splits and re-tokenizes the submitted text. Existing article paragraph rows are reused when their paragraph version still appears in the edited article. Reused paragraph versions keep their `paragraph_translations`. Changed paragraphs receive new versions and start untranslated.

After edit, article translation progress is recalculated from current paragraph versions. If every current word has a paragraph translation row, status is `done`; if some rows are preserved but some are missing, status is `stale`; otherwise status is `untranslated`.

## API/UI

Article detail responses include ordered paragraphs. The reader renders paragraphs directly and sends `article_paragraph_id` with word translation requests. A basic edit flow updates title/text through `PUT /api/v1/articles/{article_id}`.
