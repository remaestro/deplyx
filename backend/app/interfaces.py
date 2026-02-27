"""Dependency-injection interfaces (Protocols).

Every production implementation lives outside this file; tests provide
lightweight fakes that satisfy the same contracts.
"""

from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.change import Change


# ── Existing service protocols ────────────────────────────────────────


class ImpactAnalyzer(Protocol):
    async def analyze(
        self,
        target_node_ids: list[str],
        action: str | None,
        change_type: str | None,
        environment: str | None,
        title: str | None,
    ) -> dict[str, Any]:
        ...


class RiskEvaluator(Protocol):
    async def evaluate(
        self,
        change_data: dict[str, Any],
        impact_data: dict[str, Any],
    ) -> dict[str, Any]:
        ...


class WorkflowRouter(Protocol):
    async def route(
        self,
        db: AsyncSession,
        change: Change,
        risk_result: dict[str, Any],
        user_id: int | None,
    ) -> dict[str, Any]:
        ...


class NotificationSender(Protocol):
    async def send(self, title: str, body: str, metadata: dict[str, Any] | None = None) -> bool:
        ...


# ── Graph layer ───────────────────────────────────────────────────────


class IGraphClient(Protocol):
    """Abstraction over the Neo4j client used by connectors and services."""

    async def run_query(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        ...

    async def merge_node(self, label: str, node_id: str, props: dict[str, Any]) -> dict[str, Any]:
        ...

    async def create_relationship(
        self,
        from_label: str,
        from_id: str,
        rel_type: str,
        to_label: str,
        to_id: str,
        props: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...


# ── Repository protocols ─────────────────────────────────────────────


class IChangeRepository(Protocol):
    """Read/write access to the ``changes`` table."""

    async def get(self, db: AsyncSession, change_id: str) -> Change | None:
        ...

    async def set_stage(self, db: AsyncSession, change_id: str, stage: str, **kwargs: Any) -> None:
        ...

    async def increment_attempts(self, db: AsyncSession, change_id: str) -> None:
        ...


class IPolicyRepository(Protocol):
    """Access to the policy / threshold store."""

    async def get_thresholds(self, db: AsyncSession) -> Any:
        ...


class IApprovalRepository(Protocol):
    """Approval record management."""

    async def approval_exists(self, db: AsyncSession, change_id: str, role: str) -> bool:
        ...

    async def create_approval(self, db: AsyncSession, change_id: str, role: str, **kwargs: Any) -> Any:
        ...


class IAuditRepository(Protocol):
    """Audit event logging."""

    async def log_event(
        self,
        db: AsyncSession,
        *,
        event: str,
        change_id: str | int | None = None,
        trace_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        ...


# ── Alerting ──────────────────────────────────────────────────────────


class IAlertNotifier(Protocol):
    """Pluggable alert delivery (Slack, email, PagerDuty …)."""

    async def send(self, event: Any) -> None:
        ...
