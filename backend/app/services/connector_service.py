from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.aws import AWSConnector
from app.connectors.base import BaseConnector
from app.connectors.cisco import CiscoConnector
from app.connectors.checkpoint import CheckPointConnector
from app.connectors.fortinet import FortinetConnector
from app.connectors.azure import AzureConnector
from app.connectors.juniper import JuniperConnector
from app.connectors.paloalto import PaloAltoConnector
from app.models.connector import Connector
from app.utils.logging import get_logger

logger = get_logger(__name__)

CONNECTOR_CLASSES: dict[str, type] = {
    "paloalto": PaloAltoConnector,
    "fortinet": FortinetConnector,
    "cisco": CiscoConnector,
    "aws": AWSConnector,
    "checkpoint": CheckPointConnector,
    "juniper": JuniperConnector,
    "azure": AzureConnector,
}


def _get_connector_instance(connector: Connector) -> BaseConnector:
    cls = CONNECTOR_CLASSES.get(connector.connector_type)
    if cls is None:
        raise ValueError(f"Unknown connector type: {connector.connector_type}")
    return cls(connector.config)


async def create_connector(db: AsyncSession, data: dict[str, Any]) -> Connector:
    connector = Connector(**data)
    db.add(connector)
    await db.flush()
    await db.refresh(connector)
    return connector


async def get_connector(db: AsyncSession, connector_id: int) -> Connector | None:
    result = await db.execute(select(Connector).where(Connector.id == connector_id))
    return result.scalar_one_or_none()


async def list_connectors(db: AsyncSession) -> list[Connector]:
    result = await db.execute(select(Connector).order_by(Connector.id))
    return list(result.scalars().all())


async def update_connector(db: AsyncSession, connector_id: int, data: dict[str, Any]) -> Connector | None:
    connector = await get_connector(db, connector_id)
    if connector is None:
        return None
    for key, value in data.items():
        if value is not None:
            setattr(connector, key, value)
    await db.flush()
    await db.refresh(connector)
    return connector


async def delete_connector(db: AsyncSession, connector_id: int) -> bool:
    connector = await get_connector(db, connector_id)
    if connector is None:
        return False
    await db.delete(connector)
    await db.flush()
    return True


async def sync_connector(db: AsyncSession, connector_id: int) -> dict[str, Any]:
    connector = await get_connector(db, connector_id)
    if connector is None:
        return {"error": "Connector not found"}

    try:
        instance = _get_connector_instance(connector)
        result = await instance.sync()
        connector.last_sync_at = datetime.now(UTC)
        connector.status = "active" if result.get("status") == "synced" else "error"
        connector.last_error = result.get("error")
        await db.flush()
        return result
    except Exception as e:
        connector.status = "error"
        connector.last_error = str(e)
        await db.flush()
        return {"error": str(e)}


async def sync_connector_webhook(db: AsyncSession, connector_id: int, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    connector = await get_connector(db, connector_id)
    if connector is None:
        return {"error": "Connector not found"}
    if connector.sync_mode != "webhook":
        return {"error": f"Connector {connector_id} is not configured for webhook sync"}

    result = await sync_connector(db, connector_id)
    result["trigger"] = "webhook"
    result["received_payload"] = bool(payload)
    return result


async def sync_due_pull_connectors(db: AsyncSession) -> dict[str, Any]:
    result = await db.execute(
        select(Connector).where(Connector.sync_mode == "pull").order_by(Connector.id)
    )
    connectors = list(result.scalars().all())

    now = datetime.now(UTC)
    considered = len(connectors)
    synced = 0
    skipped = 0
    errors = 0
    details: list[dict[str, Any]] = []

    for connector in connectors:
        interval_minutes = connector.sync_interval_minutes if connector.sync_interval_minutes and connector.sync_interval_minutes > 0 else 60
        due_at = (connector.last_sync_at + timedelta(minutes=interval_minutes)) if connector.last_sync_at else None
        if due_at and due_at > now:
            skipped += 1
            details.append(
                {
                    "connector_id": connector.id,
                    "name": connector.name,
                    "status": "skipped_not_due",
                    "next_due_at": due_at.isoformat(),
                }
            )
            continue

        sync_result = await sync_connector(db, connector.id)
        if "error" in sync_result and sync_result.get("status") != "synced":
            errors += 1
            details.append(
                {
                    "connector_id": connector.id,
                    "name": connector.name,
                    "status": "error",
                    "error": sync_result.get("error"),
                }
            )
        else:
            synced += 1
            details.append(
                {
                    "connector_id": connector.id,
                    "name": connector.name,
                    "status": "synced",
                }
            )

    return {
        "considered": considered,
        "synced": synced,
        "skipped": skipped,
        "errors": errors,
        "details": details,
    }


async def validate_connector_change(db: AsyncSession, connector_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    connector = await get_connector(db, connector_id)
    if connector is None:
        return {"error": "Connector not found"}
    try:
        instance = _get_connector_instance(connector)
        return await instance.validate_change(payload)
    except Exception as e:
        return {"error": str(e)}


async def simulate_connector_change(db: AsyncSession, connector_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    connector = await get_connector(db, connector_id)
    if connector is None:
        return {"error": "Connector not found"}
    try:
        instance = _get_connector_instance(connector)
        return await instance.simulate_change(payload)
    except Exception as e:
        return {"error": str(e)}


async def apply_connector_change(db: AsyncSession, connector_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    connector = await get_connector(db, connector_id)
    if connector is None:
        return {"error": "Connector not found"}
    try:
        instance = _get_connector_instance(connector)
        return await instance.apply_change(payload)
    except Exception as e:
        return {"error": str(e)}
