from __future__ import annotations

from sqlalchemy import text


async def ensure_runtime_schema(conn) -> None:
    """Apply lightweight schema additions not covered by create_all."""
    await conn.execute(text(
        "ALTER TABLE articles "
        "ADD COLUMN IF NOT EXISTS translation_total_words INTEGER NOT NULL DEFAULT 0"
    ))
    await conn.execute(text(
        "ALTER TABLE articles "
        "ADD COLUMN IF NOT EXISTS translation_processed_words INTEGER NOT NULL DEFAULT 0"
    ))
    await conn.execute(text(
        "ALTER TABLE articles "
        "ADD COLUMN IF NOT EXISTS translation_total_chunks INTEGER NOT NULL DEFAULT 0"
    ))
    await conn.execute(text(
        "ALTER TABLE articles "
        "ADD COLUMN IF NOT EXISTS translation_completed_chunks INTEGER NOT NULL DEFAULT 0"
    ))
