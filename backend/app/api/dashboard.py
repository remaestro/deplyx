from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.services.dashboard_service import get_kpis

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/kpis")
async def dashboard_kpis(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await get_kpis(db)
