from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rbac import Role, require_role
from app.schemas.discovery import (
    DiscoveryBootstrapRequest,
    DiscoveryBootstrapResponse,
    DiscoveryResultRead,
    DiscoverySessionCreate,
    DiscoverySessionDetail,
    DiscoverySessionRead,
)
from app.services import discovery_service

router = APIRouter(prefix="/discovery", tags=["discovery"])


@router.post("/sessions", response_model=DiscoverySessionDetail, status_code=status.HTTP_201_CREATED)
async def create_discovery_session(
    body: DiscoverySessionCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN, Role.NETWORK)),
):
    try:
        return await discovery_service.create_discovery_session(db, body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/sessions", response_model=list[DiscoverySessionRead])
async def list_discovery_sessions(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN, Role.NETWORK)),
):
    return await discovery_service.list_discovery_sessions(db)


@router.get("/sessions/{session_id}", response_model=DiscoverySessionDetail)
async def get_discovery_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN, Role.NETWORK)),
):
    session = await discovery_service.get_discovery_session(db, session_id, include_results=True)
    if session is None:
        raise HTTPException(status_code=404, detail="Discovery session not found")
    return session


@router.get("/sessions/{session_id}/results", response_model=list[DiscoveryResultRead])
async def list_discovery_results(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN, Role.NETWORK)),
):
    session = await discovery_service.get_discovery_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Discovery session not found")
    return await discovery_service.list_discovery_results(db, session_id)


@router.post("/sessions/{session_id}/bootstrap", response_model=DiscoveryBootstrapResponse)
async def bootstrap_discovery_session(
    session_id: int,
    body: DiscoveryBootstrapRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN, Role.NETWORK)),
):
    try:
        return await discovery_service.bootstrap_discovery_session(db, session_id, body.model_dump())
    except ValueError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc