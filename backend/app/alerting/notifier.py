from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol


@dataclass
class AlertEvent:
    """Structured alert payload sent through the notifier pipeline."""

    event_type: str
    change_id: int | str
    attempts: int
    last_error: str | None
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()


class Notifier(Protocol):
    async def send(self, title: str, body: str, metadata: dict[str, Any] | None = None) -> bool:
        ...


class NoopNotifier:
    async def send(self, title: str, body: str, metadata: dict[str, Any] | None = None) -> bool:
        return False


def get_notifier() -> Notifier:
    from app.core.config import settings
    from app.alerting.slack_notifier import SlackNotifier

    if settings.slack_webhook_url:
        return SlackNotifier(settings.slack_webhook_url)
    return NoopNotifier()
