"""Shared mutable state for lab mock devices.

Each mock device imports ``DeviceState`` and uses it to track readiness,
configuration artefacts, and last-sync metadata in a thread-safe manner.
"""

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class DeviceState:
    """Thread-safe wrapper around a dict of device artefacts."""

    ready: bool = False
    last_sync_at: str | None = None
    _data: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # --- public API ---

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def update(self, mapping: dict[str, Any]) -> None:
        with self._lock:
            self._data.update(mapping)

    def snapshot(self) -> dict[str, Any]:
        """Return a shallow copy of the internal data."""
        with self._lock:
            return dict(self._data)

    def mark_synced(self) -> None:
        with self._lock:
            self.last_sync_at = datetime.now(UTC).isoformat()

    def mark_ready(self) -> None:
        with self._lock:
            self.ready = True

    def as_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "ready": self.ready,
                "last_sync_at": self.last_sync_at,
                "data": dict(self._data),
            }
