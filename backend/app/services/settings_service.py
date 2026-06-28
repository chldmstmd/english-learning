import json
from pathlib import Path

_PATH = Path(__file__).resolve().parent.parent.parent / "settings.json"
_DEFAULTS: dict = {
    "use_free_translation_fallback": True,
    "auto_open_sidebar_on_mark": True,
    "ai_provider": "deepseek",
}


def load() -> dict:
    if _PATH.exists():
        try:
            return {**_DEFAULTS, **json.loads(_PATH.read_text())}
        except Exception:
            pass
    return _DEFAULTS.copy()


def save(updates: dict) -> dict:
    current = load()
    current.update(updates)
    _PATH.write_text(json.dumps(current))
    return current
