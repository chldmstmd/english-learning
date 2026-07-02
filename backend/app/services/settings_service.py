import json
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_settings import UserSettings

_PATH = Path(__file__).resolve().parent.parent.parent / "settings.json"
_SYSTEM_DEFAULTS: dict = {
    "ai_provider": "deepseek",
}
_USER_DEFAULTS: dict = {
    "use_free_translation_fallback": True,
    "auto_open_sidebar_on_mark": True,
}
_DEFAULTS: dict = {**_SYSTEM_DEFAULTS, **_USER_DEFAULTS}
_USER_SETTING_KEYS = frozenset(_USER_DEFAULTS)


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


def _user_defaults() -> dict:
    settings = load()
    return {
        key: bool(settings.get(key, default))
        for key, default in _USER_DEFAULTS.items()
    }


def _user_settings_dict(settings: UserSettings) -> dict:
    return {
        "use_free_translation_fallback": settings.use_free_translation_fallback,
        "auto_open_sidebar_on_mark": settings.auto_open_sidebar_on_mark,
    }


async def load_user_preferences(db: AsyncSession, user_id: str) -> dict:
    settings = await db.get(UserSettings, user_id)
    if settings is None:
        return _user_defaults()
    return _user_settings_dict(settings)


async def save_user_preferences(db: AsyncSession, user_id: str, updates: dict) -> dict:
    settings = await db.get(UserSettings, user_id)
    if settings is None:
        settings = UserSettings(user_id=user_id, **_user_defaults())
        db.add(settings)

    for key, value in updates.items():
        if key in _USER_SETTING_KEYS:
            setattr(settings, key, bool(value))

    await db.commit()
    await db.refresh(settings)
    return _user_settings_dict(settings)
