from datetime import datetime, timezone, timedelta
import random

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rbac import Role, require_role
from app.schemas.connector import ConnectorCreate, ConnectorRead, ConnectorUpdate
from app.services import connector_service

router = APIRouter(prefix="/connectors", tags=["connectors"])


@router.post("", response_model=ConnectorRead, status_code=status.HTTP_201_CREATED)
async def create_connector(
    body: ConnectorCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN)),
):
    return await connector_service.create_connector(db, body.model_dump())


@router.get("", response_model=list[ConnectorRead])
async def list_connectors(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN, Role.NETWORK)),
):
    return await connector_service.list_connectors(db)


@router.get("/{connector_id}", response_model=ConnectorRead)
async def get_connector(
    connector_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN, Role.NETWORK)),
):
    conn = await connector_service.get_connector(db, connector_id)
    if conn is None:
        raise HTTPException(status_code=404, detail="Connector not found")
    return conn


@router.put("/{connector_id}", response_model=ConnectorRead)
async def update_connector(
    connector_id: int,
    body: ConnectorUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN)),
):
    updated = await connector_service.update_connector(db, connector_id, body.model_dump(exclude_unset=True))
    if updated is None:
        raise HTTPException(status_code=404, detail="Connector not found")
    return updated


@router.delete("/{connector_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connector(
    connector_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN)),
):
    deleted = await connector_service.delete_connector(db, connector_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Connector not found")


@router.post("/{connector_id}/sync")
async def sync_connector(
    connector_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN, Role.NETWORK)),
):
    result = await connector_service.sync_connector(db, connector_id)
    if "error" in result and result.get("status") != "error":
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/{connector_id}/webhook")
async def webhook_sync_connector(
    connector_id: int,
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN, Role.NETWORK)),
):
    result = await connector_service.sync_connector_webhook(db, connector_id, payload)
    if "error" in result and result.get("status") != "error":
        if result["error"] == "Connector not found":
            raise HTTPException(status_code=404, detail=result["error"])
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/sync/pull")
async def sync_pull_connectors(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN)),
):
    return await connector_service.sync_due_pull_connectors(db)


@router.post("/{connector_id}/validate")
async def validate_connector_change(
    connector_id: int,
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN, Role.NETWORK, Role.SECURITY)),
):
    result = await connector_service.validate_connector_change(db, connector_id, payload)
    if "error" in result:
        if result["error"] == "Connector not found":
            raise HTTPException(status_code=404, detail=result["error"])
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/{connector_id}/simulate")
async def simulate_connector_change(
    connector_id: int,
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN, Role.NETWORK, Role.SECURITY)),
):
    result = await connector_service.simulate_connector_change(db, connector_id, payload)
    if "error" in result:
        if result["error"] == "Connector not found":
            raise HTTPException(status_code=404, detail=result["error"])
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/{connector_id}/apply")
async def apply_connector_change(
    connector_id: int,
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN, Role.NETWORK, Role.SECURITY)),
):
    result = await connector_service.apply_connector_change(db, connector_id, payload)
    if "error" in result:
        if result["error"] == "Connector not found":
            raise HTTPException(status_code=404, detail=result["error"])
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/{connector_id}/sync-history")
async def connector_sync_history(
    connector_id: int,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN, Role.NETWORK)),
):
    """Return recent sync history for a connector.

    Stub implementation — generates mock history entries.
    Replace with real audit-log queries once sync events are persisted.
    """
    conn = await connector_service.get_connector(db, connector_id)
    if conn is None:
        raise HTTPException(status_code=404, detail="Connector not found")

    now = datetime.now(timezone.utc)
    entries = []
    for i in range(min(limit, 20)):
        success = random.random() > 0.15
        ts = now - timedelta(hours=i * 6, minutes=random.randint(0, 59))
        entries.append({
            "id": i + 1,
            "connector_id": connector_id,
            "timestamp": ts.isoformat(),
            "status": "success" if success else "error",
            "devices_synced": random.randint(5, 40) if success else 0,
            "duration_ms": random.randint(800, 12000),
            "error": None if success else "Connection timed out",
        })

    return entries
