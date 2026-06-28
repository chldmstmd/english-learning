from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.services import settings_service

router = APIRouter(tags=["settings"])


class SettingsOut(BaseModel):
    use_free_translation_fallback: bool
    auto_open_sidebar_on_mark: bool


class SettingsIn(BaseModel):
    use_free_translation_fallback: Optional[bool] = None
    auto_open_sidebar_on_mark: Optional[bool] = None


@router.get("/settings", response_model=SettingsOut)
async def get_settings():
    return settings_service.load()


@router.patch("/settings", response_model=SettingsOut)
async def update_settings(body: SettingsIn):
    updates = body.model_dump(exclude_none=True)
    return settings_service.save(updates)
