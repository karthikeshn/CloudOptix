from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.sql import text
from typing import List, Dict, Any
from datetime import datetime, timedelta

from app.core.database import get_db
from app.models.system.system_notification import SystemNotification
from app.schemas.system.system_notification import SystemNotificationResponse

router = APIRouter(prefix="/notifications", tags=["Notifications"])

@router.get("", response_model=List[SystemNotificationResponse])
async def get_notifications(limit: int = 50, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SystemNotification)
        .order_by(SystemNotification.created_at.desc())
        .limit(limit)
    )
    notifications = result.scalars().all()
    return notifications

@router.post("/mark-read")
async def mark_read(payload: dict, db: AsyncSession = Depends(get_db)):
    notification_id = payload.get("id")
    if notification_id:
        await db.execute(
            update(SystemNotification)
            .where(SystemNotification.id == notification_id)
            .values(is_read=True)
        )
    else:
        # Mark all as read
        await db.execute(
            update(SystemNotification)
            .where(SystemNotification.is_read == False)
            .values(is_read=True)
        )
    await db.commit()
    return {"status": "success"}

@router.delete("/cleanup")
async def cleanup_notifications(days: int = 2, db: AsyncSession = Depends(get_db)):
    cutoff = datetime.utcnow() - timedelta(days=days)
    result = await db.execute(
        delete(SystemNotification)
        .where(SystemNotification.created_at < cutoff)
    )
    await db.commit()
    return {"status": "success", "deleted": result.rowcount}

