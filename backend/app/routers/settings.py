from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services import settings_service

router = APIRouter(tags=["settings"])


class SettingsOut(BaseModel):
    use_free_translation_fallback: bool
    auto_open_sidebar_on_mark: bool


class SettingsIn(BaseModel):
    use_free_translation_fallback: Optional[bool] = None
    auto_open_sidebar_on_mark: Optional[bool] = None


@router.get("/settings", response_model=SettingsOut)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return SettingsOut(**await settings_service.load_user_preferences(db, current_user.id))


@router.patch("/settings", response_model=SettingsOut)
async def update_settings(
    body: SettingsIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    updates = body.model_dump(exclude_none=True)
    return SettingsOut(**await settings_service.save_user_preferences(db, current_user.id, updates))
