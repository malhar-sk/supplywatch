"""Guest-mode route. Deliberately has no require_api_key dependency and no
authentication of any kind — this is the free, no-signup entry point
described in Chapter 1.1 / 1.4.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.database import get_db
from snapshot.guest import get_guest_brief

router = APIRouter(prefix="/guest", tags=["guest"])


@router.get("/demo")
async def guest_demo(db: AsyncSession = Depends(get_db)):
    brief = await get_guest_brief(db)
    return {
        "data": brief,
        "meta": {"timestamp": datetime.now(timezone.utc), "version": get_settings().app_version},
    }
