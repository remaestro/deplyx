"""Configuration centralisée pour les connecteurs V1 et V2.

Tous les timeouts, TTL, limites et autres réglages sont ici,
lus depuis les variables d'environnement au premier import.

Utilisation :
    from app.connectors_v2.config import CONFIG

    timeout = CONFIG.ssh_conn_timeout
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConnectorConfig:
    # ── SSH ──────────────────────────────────────────────────────
    ssh_conn_timeout: int = field(
        default_factory=lambda: int(os.environ.get("SSH_CONN_TIMEOUT", "8"))
    )
    ssh_cmd_timeout: int = field(
        default_factory=lambda: int(os.environ.get("SSH_CMD_TIMEOUT", "15"))
    )
    ssh_banner_timeout: int = field(
        default_factory=lambda: int(os.environ.get("SSH_BANNER_TIMEOUT", "8"))
    )
    ssh_auth_timeout: int = field(
        default_factory=lambda: int(os.environ.get("SSH_AUTH_TIMEOUT", "8"))
    )

    # ── API REST ─────────────────────────────────────────────────
    api_timeout: int = field(
        default_factory=lambda: int(os.environ.get("API_TIMEOUT", "8"))
    )

    # ── Opérations ───────────────────────────────────────────────
    sync_timeout: int = field(
        default_factory=lambda: int(os.environ.get("SYNC_TIMEOUT", "300"))
    )
    operation_timeout: int = field(
        default_factory=lambda: int(os.environ.get("OPERATION_TIMEOUT", "90"))
    )

    # ── Cache & Circuit breaker ──────────────────────────────────
    fingerprint_ttl: int = field(
        default_factory=lambda: int(os.environ.get("FINGERPRINT_TTL_SECONDS", "3600"))
    )
    circuit_breaker_reset: int = field(
        default_factory=lambda: int(
            os.environ.get("CIRCUIT_BREAKER_RESET_SECONDS", "120")
        )
    )

    # ── Concurrence ──────────────────────────────────────────────
    sync_semaphore: int = field(
        default_factory=lambda: int(os.environ.get("SYNC_SEMAPHORE", "20"))
    )

    # ── Files d'attente d'opérations (pull) ──────────────────────
    pull_default_interval_minutes: int = field(default=60)

    def to_dict(self) -> dict[str, Any]:
        """Sérialisation pour debug / API."""
        return {
            k: v
            for k, v in self.__dict__.items()
            if not k.startswith("_")
        }


# Instance singleton importable
CONFIG = ConnectorConfig()
