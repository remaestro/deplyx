from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class SyncResult:
    """Outcome of a connector sync() call.

    Tracks per-entity-type success/failure counts so the caller can
    distinguish full-sync, partial-sync and total-error.
    """

    status: Literal["synced", "partial", "error"] = "synced"
    synced: dict[str, int] = field(default_factory=dict)
    failed: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def record_success(self, entity_type: str) -> None:
        self.synced[entity_type] = self.synced.get(entity_type, 0) + 1

    def record_failure(self, entity_type: str, error: str) -> None:
        self.failed[entity_type] = self.failed.get(entity_type, 0) + 1
        self.errors.append(f"{entity_type}: {error}")

    def finalise(self) -> None:
        has_synced = any(v > 0 for v in self.synced.values())
        has_failed = any(v > 0 for v in self.failed.values())
        if has_synced and has_failed:
            self.status = "partial"
        elif has_failed and not has_synced:
            self.status = "error"
        else:
            self.status = "synced"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "synced": dict(self.synced),
            "failed": dict(self.failed),
            "errors": list(self.errors),
        }


class BaseConnector(ABC):
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        operation = (request or {}).get("operation")
        payload = (request or {}).get("input") or {}

        if operation == "sync":
            return await self.sync()
        if operation == "validate":
            return await self.validate_change(payload)
        if operation == "simulate":
            return await self.simulate_change(payload)
        if operation == "apply":
            return await self.apply_change(payload)

        return {
            "status": "error",
            "error": f"Unsupported connector operation: {operation}",
        }

    async def sync(self) -> dict[str, Any]:
        raise NotImplementedError

    async def validate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    async def simulate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    async def apply_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError
