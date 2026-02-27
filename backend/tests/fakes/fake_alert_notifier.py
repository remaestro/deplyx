"""Fake alert notifier for unit tests.

Records all alerts in a list so tests can inspect them.
"""

from typing import Any

from app.alerting.notifier import AlertEvent


class FakeAlertNotifier:
    """In-memory alert notifier satisfying IAlertNotifier."""

    def __init__(self) -> None:
        self.events: list[AlertEvent] = []
        self.send_calls: list[dict[str, Any]] = []

    async def send(
        self,
        title: str,
        body: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        self.send_calls.append({"title": title, "body": body, "metadata": metadata})
        return True

    def record(self, event: AlertEvent) -> None:
        self.events.append(event)
