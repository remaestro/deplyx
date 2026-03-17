import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from time import perf_counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.base import BaseConnector
from app.connectors.cisco import CiscoConnector
from app.connectors.checkpoint import CheckPointConnector
from app.connectors.fortinet import FortinetConnector
from app.connectors.juniper import JuniperConnector
from app.connectors.paloalto import PaloAltoConnector
from app.connectors.aruba_switch import ArubaSwitchConnector
from app.connectors.aruba_ap import ArubaAPConnector
from app.connectors.cisco_nxos import CiscoNXOSConnector
from app.connectors.cisco_ftd import CiscoFTDConnector
from app.connectors.cisco_router import CiscoRouterConnector
from app.connectors.cisco_wlc import CiscoWLCConnector
from app.connectors.vyos import VyOSConnector
from app.connectors.strongswan_vpn import StrongSwanVPNConnector
from app.connectors.snort_ids import SnortIDSConnector
from app.connectors.openldap import OpenLDAPConnector
from app.connectors.nginx_app import NginxAppConnector
from app.connectors.postgres_app import PostgresAppConnector
from app.connectors.redis_app import RedisAppConnector
from app.connectors.elasticsearch import ElasticsearchConnector
from app.connectors.grafana import GrafanaConnector
from app.connectors.prometheus import PrometheusConnector
from app.models.connector import Connector
from app.services import change_service
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Allow all connectors to sync concurrently.  Each connector already
# offloads blocking I/O to a thread via asyncio.to_thread(), and
# per-command timeouts (30 s) + overall operation timeout (90 s) prevent
# any single sync from monopolising resources.
_SYNC_SEMAPHORE = asyncio.Semaphore(20)

CONNECTOR_CLASSES: dict[str, type] = {
    "paloalto": PaloAltoConnector,
    "fortinet": FortinetConnector,
    "cisco": CiscoConnector,
    "checkpoint": CheckPointConnector,
    "juniper": JuniperConnector,
    "aruba-switch": ArubaSwitchConnector,
    "aruba-ap": ArubaAPConnector,
    "cisco-nxos": CiscoNXOSConnector,
    "cisco-ftd": CiscoFTDConnector,
    "cisco-router": CiscoRouterConnector,
    "cisco-wlc": CiscoWLCConnector,
    "vyos": VyOSConnector,
    "strongswan": StrongSwanVPNConnector,
    "snort": SnortIDSConnector,
    "openldap": OpenLDAPConnector,
    "nginx": NginxAppConnector,
    "postgres": PostgresAppConnector,
    "redis": RedisAppConnector,
    "elasticsearch": ElasticsearchConnector,
    "grafana": GrafanaConnector,
    "prometheus": PrometheusConnector,
}


def _get_connector_instance(connector: Connector) -> BaseConnector:
    cls = CONNECTOR_CLASSES.get(connector.connector_type)
    if cls is None:
        raise ValueError(f"Unknown connector type: {connector.connector_type}")
    return cls(connector.config)


def _is_v2_result(result: dict[str, Any]) -> bool:
    return result.get("contract_version") == "2.0" and "ok" in result and "status" in result


def _sync_success(result: dict[str, Any]) -> bool:
    if _is_v2_result(result):
        return bool(result.get("ok"))
    return result.get("status") == "synced"


def _extract_error_message(result: dict[str, Any]) -> str | None:
    if _is_v2_result(result):
        errors = result.get("errors") or []
        if errors:
            first = errors[0]
            if isinstance(first, dict):
                return first.get("message")
        return None
    return result.get("error")


def _legacy_payload(result: dict[str, Any]) -> dict[str, Any]:
    if _is_v2_result(result):
        data = result.get("data")
        if isinstance(data, dict):
            return data
    return result


def _normalize_operation_result(
    *,
    connector: Connector,
    operation: str,
    result: dict[str, Any],
    duration_ms: int,
) -> dict[str, Any]:
    if _is_v2_result(result):
        normalized = {
            "contract_version": "2.0",
            "operation": result.get("operation", operation),
            "connector_type": result.get("connector_type", connector.connector_type),
            "ok": bool(result.get("ok")),
            "status": result.get("status", "success" if result.get("ok") else "failed"),
            "summary": result.get("summary", f"{operation} completed"),
            "data": result.get("data") if isinstance(result.get("data"), dict) else {},
            "changes": result.get("changes") if isinstance(result.get("changes"), list) else [],
            "artifacts": result.get("artifacts") if isinstance(result.get("artifacts"), dict) else {},
            "metrics": result.get("metrics") if isinstance(result.get("metrics"), dict) else {},
            "errors": result.get("errors") if isinstance(result.get("errors"), list) else [],
        }
        normalized["metrics"].setdefault("duration_ms", duration_ms)
        return normalized

    has_error = bool(result.get("error"))
    if operation == "sync":
        ok = result.get("status") == "synced" and not has_error
    elif operation == "validate":
        ok = bool(result.get("valid")) and not has_error
    elif operation == "apply":
        ok = bool(result.get("applied")) and not has_error
    else:
        ok = not has_error

    status = "success" if ok else "failed"
    errors = []
    if has_error:
        errors.append({"code": "connector_error", "message": str(result.get("error")), "retryable": False})

    return {
        "contract_version": "2.0",
        "operation": operation,
        "connector_type": connector.connector_type,
        "ok": ok,
        "status": status,
        "summary": f"{connector.name}: {operation} {status}",
        "data": result,
        "changes": [],
        "artifacts": {},
        "metrics": {"duration_ms": duration_ms},
        "errors": errors,
    }


async def execute_connector_operation(
    db: AsyncSession,
    connector_id: int,
    operation: str,
    payload: dict[str, Any] | None = None,
    *,
    action: str | None = None,
    context: dict[str, Any] | None = None,
    target: dict[str, Any] | None = None,
    normalize: bool = True,
) -> dict[str, Any]:
    connector = await get_connector(db, connector_id)
    if connector is None:
        error_result = {
            "contract_version": "2.0",
            "operation": operation,
            "connector_type": "unknown",
            "ok": False,
            "status": "failed",
            "summary": "Connector not found",
            "data": {},
            "changes": [],
            "artifacts": {},
            "metrics": {"duration_ms": 0},
            "errors": [{"code": "not_found", "message": "Connector not found", "retryable": False}],
        }
        return error_result if normalize else {"error": "Connector not found"}

    started = perf_counter()
    try:
        logger.warning("  [exec_op] connector=%s(%s) op=%s — waiting for semaphore", connector.id, connector.connector_type, operation)
        async with _SYNC_SEMAPHORE:
            logger.warning("  [exec_op] connector=%s(%s) op=%s — acquired semaphore, creating instance", connector.id, connector.connector_type, operation)
            instance = _get_connector_instance(connector)
            request = {
                "contract_version": "2.0",
                "operation": operation,
                "action": action,
                "input": payload or {},
                "context": context or {},
                "target": target or {},
            }
            if hasattr(instance, "run") and callable(getattr(instance, "run")):
                logger.warning("  [exec_op] connector=%s — calling instance.run(%s)", connector.id, operation)
                raw_result = await asyncio.wait_for(instance.run(request), timeout=90)
            else:
                payload_data = payload or {}
                if operation == "sync":
                    logger.warning("  [exec_op] connector=%s — calling instance.sync()", connector.id)
                    raw_result = await asyncio.wait_for(instance.sync(), timeout=90)
                elif operation == "validate":
                    raw_result = await asyncio.wait_for(instance.validate_change(payload_data), timeout=90)
                elif operation == "simulate":
                    raw_result = await asyncio.wait_for(instance.simulate_change(payload_data), timeout=90)
                elif operation == "apply":
                    raw_result = await asyncio.wait_for(instance.apply_change(payload_data), timeout=90)
                else:
                    raw_result = {"status": "error", "error": f"Unsupported connector operation: {operation}"}
            logger.warning("  [exec_op] connector=%s op=%s — returned status=%s  (%.0fms)", connector.id, operation, raw_result.get('status','?'), (perf_counter()-started)*1000)
    except asyncio.TimeoutError:
        elapsed = perf_counter() - started
        logger.error("  [exec_op] connector=%s op=%s — TIMEOUT after %.0fs", connector.id, operation, elapsed)
        connector.status = "error"
        connector.last_error = f"Timeout after {elapsed:.0f}s"
        await db.flush()
        if not normalize:
            return {"error": f"Timeout after {elapsed:.0f}s"}
        duration_ms = int(elapsed * 1000)
        return {
            "contract_version": "2.0",
            "operation": operation,
            "connector_type": connector.connector_type,
            "ok": False,
            "status": "failed",
            "summary": f"{connector.name}: {operation} timed out after {elapsed:.0f}s",
            "data": {},
            "changes": [],
            "artifacts": {},
            "errors": [f"Timeout after {elapsed:.0f}s"],
            "duration_ms": duration_ms,
        }
    except Exception as exc:
        logger.error("  [exec_op] connector=%s op=%s — EXCEPTION: %s", connector.id, operation, exc)
        connector.status = "error"
        connector.last_error = str(exc)
        await db.flush()
        if not normalize:
            return {"error": str(exc)}
        duration_ms = int((perf_counter() - started) * 1000)
        return {
            "contract_version": "2.0",
            "operation": operation,
            "connector_type": connector.connector_type,
            "ok": False,
            "status": "failed",
            "summary": f"{connector.name}: {operation} failed",
            "data": {},
            "changes": [],
            "artifacts": {},
            "metrics": {"duration_ms": duration_ms},
            "errors": [{"code": "exception", "message": str(exc), "retryable": False}],
        }

    duration_ms = int((perf_counter() - started) * 1000)
    normalized_result = _normalize_operation_result(
        connector=connector,
        operation=operation,
        result=raw_result,
        duration_ms=duration_ms,
    )

    if operation == "sync":
        connector.last_sync_at = datetime.now(UTC)
        connector.status = "active" if _sync_success(raw_result) else "error"
        connector.last_error = _extract_error_message(raw_result)
        # Persist SyncResult detail (status/synced/failed/errors)
        if "synced" in raw_result or "failed" in raw_result:
            connector.last_sync_detail = {
                k: raw_result[k]
                for k in ("status", "synced", "failed", "errors")
                if k in raw_result
            }
        await db.flush()

    if normalize:
        return normalized_result
    return _legacy_payload(raw_result)


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


async def sync_connector(db: AsyncSession, connector_id: int, *, rerun_changes: bool = True) -> dict[str, Any]:
    result = await execute_connector_operation(db, connector_id, "sync", normalize=False)
    if rerun_changes and result.get("status") == "synced":
        await _rerun_all_changes_analysis(db, trigger="connector_sync")
    return result


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

        sync_result = await sync_connector(db, connector.id, rerun_changes=False)
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

    if synced > 0:
        await _rerun_all_changes_analysis(db, trigger="pull_sync")

    return {
        "considered": considered,
        "synced": synced,
        "skipped": skipped,
        "errors": errors,
        "details": details,
    }


async def reset_all_connector_sync_state(db: AsyncSession) -> int:
    result = await db.execute(select(Connector))
    connectors = list(result.scalars().all())
    for connector in connectors:
        connector.last_sync_at = None
        connector.status = "inactive"
        connector.last_error = None
    await db.flush()
    return len(connectors)


async def _rerun_all_changes_analysis(db: AsyncSession, trigger: str) -> None:
    try:
        count = await change_service.enqueue_analysis_for_all_changes(db)
        logger.info("Reran analysis for %d changes (trigger=%s)", count, trigger)
    except Exception as exc:
        logger.warning("Unable to rerun change analysis after sync (trigger=%s): %s", trigger, exc)


async def validate_connector_change(db: AsyncSession, connector_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    return await execute_connector_operation(db, connector_id, "validate", payload, normalize=False)


async def simulate_connector_change(db: AsyncSession, connector_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    return await execute_connector_operation(db, connector_id, "simulate", payload, normalize=False)


async def apply_connector_change(db: AsyncSession, connector_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    return await execute_connector_operation(db, connector_id, "apply", payload, normalize=False)
