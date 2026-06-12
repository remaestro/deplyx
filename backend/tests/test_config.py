"""Tests pour le module config (timeouts centralisés)."""

from __future__ import annotations

import os

import pytest

from app.connectors_v2.config import ConnectorConfig, CONFIG


class TestConnectorConfig:
    def test_defaults(self):
        """Les valeurs par défaut doivent être présentes."""
        cfg = ConnectorConfig()
        assert cfg.ssh_conn_timeout == 8
        assert cfg.ssh_cmd_timeout == 15
        assert cfg.ssh_banner_timeout == 8
        assert cfg.ssh_auth_timeout == 8
        assert cfg.api_timeout == 8
        assert cfg.sync_timeout == 300
        assert cfg.operation_timeout == 90
        assert cfg.fingerprint_ttl == 3600
        assert cfg.circuit_breaker_reset == 120
        assert cfg.sync_semaphore == 20
        assert cfg.pull_default_interval_minutes == 60

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch):
        """Les variables d'environnement doivent surcharger les défauts."""
        monkeypatch.setenv("SSH_CONN_TIMEOUT", "5")
        monkeypatch.setenv("SSH_CMD_TIMEOUT", "10")
        monkeypatch.setenv("SYNC_TIMEOUT", "600")
        monkeypatch.setenv("FINGERPRINT_TTL_SECONDS", "7200")
        monkeypatch.setenv("CIRCUIT_BREAKER_RESET_SECONDS", "300")
        monkeypatch.setenv("SYNC_SEMAPHORE", "10")

        cfg = ConnectorConfig()
        assert cfg.ssh_conn_timeout == 5
        assert cfg.ssh_cmd_timeout == 10
        assert cfg.sync_timeout == 600
        assert cfg.fingerprint_ttl == 7200
        assert cfg.circuit_breaker_reset == 300
        assert cfg.sync_semaphore == 10

    def test_singleton(self):
        """CONFIG doit être une instance de ConnectorConfig."""
        assert isinstance(CONFIG, ConnectorConfig)

    def test_to_dict(self):
        """to_dict() doit retourner un dict avec toutes les clés."""
        d = CONFIG.to_dict()
        assert isinstance(d, dict)
        assert "ssh_conn_timeout" in d
        assert "sync_semaphore" in d
