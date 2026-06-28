from app.translation_engine import GoogleFallbackTranslator


async def translate(word: str) -> str:
    return await GoogleFallbackTranslator().translate(word)
