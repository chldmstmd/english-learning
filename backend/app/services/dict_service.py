import httpx

_DICT_API_BASE = "https://api.dictionaryapi.dev/api/v2/entries/en"


async def get_word_data(word: str) -> dict:
    """
    Fetch phonetic + definitions from Free Dictionary API.
    Returns {"phonetic": str|None, "definitions": list[dict]}
    """
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get(f"{_DICT_API_BASE}/{word}")
            if resp.status_code != 200:
                return {"phonetic": None, "definitions": []}
            data = resp.json()
            if not data or not isinstance(data, list):
                return {"phonetic": None, "definitions": []}
            entry = data[0]
            return {
                "phonetic": entry.get("phonetic") or _extract_phonetic(entry),
                "definitions": _extract_definitions(entry),
            }
        except Exception:
            return {"phonetic": None, "definitions": []}


async def get_first_definition(word: str) -> str:
    """Return the first definition string, fallback to word itself."""
    data = await get_word_data(word)
    if data["definitions"]:
        return data["definitions"][0].get("definition", word)
    return word


def _extract_phonetic(entry: dict) -> str | None:
    for p in entry.get("phonetics", []):
        if p.get("text"):
            return p["text"]
    return None


def _extract_definitions(entry: dict) -> list[dict]:
    results = []
    for meaning in entry.get("meanings", []):
        pos = meaning.get("partOfSpeech", "")
        for defn in meaning.get("definitions", [])[:2]:
            results.append({
                "pos": pos,
                "definition": defn.get("definition", ""),
                "example": defn.get("example", ""),
            })
    return results[:6]
