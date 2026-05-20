import asyncio

from deep_translator import GoogleTranslator


async def translate(word: str) -> str:
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: GoogleTranslator(source="en", target="zh-CN").translate(word),
    )
    return result
