"""Fake repository implementations for unit tests.

These in-memory stores satisfy the repository protocols defined in
``app.interfaces`` without requiring a real database.
"""

from datetime import UTC, datetime
from typing import Any


class FakeChangeRepository:
    """In-memory change store satisfying IChangeRepository."""

    def __init__(self) -> None:
        self._changes: dict[int, dict[str, Any]] = {}
        self._next_id = 1

    async def get(self, change_id: int) -> dict[str, Any] | None:
        return self._changes.get(change_id)

    async def save(self, change: dict[str, Any]) -> dict[str, Any]:
        if "id" not in change:
            change["id"] = self._next_id
            self._next_id += 1
        self._changes[change["id"]] = change
        return change

    async def list_all(self) -> list[dict[str, Any]]:
        return list(self._changes.values())


class FakePolicyRepository:
    """In-memory policy store satisfying IPolicyRepository."""

    def __init__(self, policies: list[dict[str, Any]] | None = None) -> None:
        self._policies = list(policies or [])

    async def get_active(self, name: str) -> dict[str, Any] | None:
        for p in self._policies:
            if p.get("name") == name and p.get("is_active", True):
                return p
        return None

    async def list_all(self) -> list[dict[str, Any]]:
        return list(self._policies)


class FakeApprovalRepository:
    """In-memory approval store satisfying IApprovalRepository."""

    def __init__(self) -> None:
        self._approvals: list[dict[str, Any]] = []

    async def create(self, approval: dict[str, Any]) -> dict[str, Any]:
        approval.setdefault("created_at", datetime.now(UTC).isoformat())
        self._approvals.append(approval)
        return approval

    async def list_for_change(self, change_id: int) -> list[dict[str, Any]]:
        return [a for a in self._approvals if a.get("change_id") == change_id]


class FakeAuditRepository:
    """In-memory audit log satisfying IAuditRepository."""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def log(self, entry: dict[str, Any]) -> None:
        entry.setdefault("timestamp", datetime.now(UTC).isoformat())
        self.entries.append(entry)

    async def list_all(self) -> list[dict[str, Any]]:
        return list(self.entries)
