from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_content_admin
from app.models.sync_log import VoaSyncLog
from app.models.user import User
from app.services import voa_service

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/sync-voa", summary="Manually trigger VOA RSS sync")
async def sync_voa(
    current_user: User = Depends(require_content_admin),
):
    """Immediately triggers a full VOA feed sync. May take up to a few minutes."""
    results = await voa_service.sync_all_feeds()
    total_new = sum(r["new_articles"] for r in results)
    return {"results": results, "total_new_articles": total_new}


@router.get("/sync-voa/logs", summary="View VOA sync history")
async def get_sync_logs(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_content_admin),
):
    rows = list(await db.scalars(
        select(VoaSyncLog).order_by(VoaSyncLog.synced_at.desc()).limit(limit)
    ))
    return [
        {
            "id": r.id,
            "feed_url": r.feed_url,
            "synced_at": r.synced_at,
            "new_articles": r.new_articles,
            "status": r.status,
            "error_message": r.error_message,
        }
        for r in rows
    ]
