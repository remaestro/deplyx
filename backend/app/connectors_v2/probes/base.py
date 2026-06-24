"""Probe contract — transport-specialized device identification & collection.

The orchestration (scan → profile match → connector create/update → Neo4j →
topology) is **unified** in the scanner and ``UnifiedConnector``. The
transport-specific behaviour (SSH/CLI vs API/OAuth) is **specialized** behind
the :class:`Probe` contract.

A probe answers two questions:

``identify(creds)``
    Who is this device? (vendor/os/version/hostname/model) — used by the
    scanner and by ``UnifiedConnector._discover``.

``collect(creds)``
    Pull the inventory and push it to Neo4j — only implemented by probes that
    own a non-standard collection path (e.g. the FDM/OAuth API for Cisco FTD).
    For plain SSH/CLI devices the unified profile-driven engine in
    ``UnifiedConnector`` performs collection, so ``owns_collection`` returns
    ``False``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class ProbeCredentials:
    """All connection material a probe may need."""

    host: str
    username: str = ""
    password: str = ""
    enable_password: str = ""
    api_username: str = ""
    api_password: str = ""
    port: int = 22
    api_port: int = 443
    verify_ssl: bool = False
    transport_mode: str = "auto"  # auto | ssh | api

    @property
    def has_ssh(self) -> bool:
        return bool(self.username and self.password)

    @property
    def has_api(self) -> bool:
        return bool(self.api_username and self.api_password)


@dataclass
class Identity:
    """Result of a probe's identification attempt."""

    vendor: str | None = None
    os: str | None = None
    os_version: str | None = None
    hostname: str | None = None
    model: str | None = None
    transport: str | None = None
    source: str = "unknown"

    def is_identified(self) -> bool:
        return bool(self.vendor)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Probe(ABC):
    """Transport-specialized identification & (optional) collection plugin."""

    #: Human-readable probe name.
    name: str = "probe"
    #: Transport family this probe drives ("ssh" or "api").
    transport: str = "ssh"

    def supports(self, creds: ProbeCredentials) -> bool:
        """Whether this probe has the credentials needed to attempt ``identify``."""
        return True

    @abstractmethod
    def identify(self, creds: ProbeCredentials) -> Identity | None:
        """Identify the device, or return ``None``/un-identified on failure."""
        raise NotImplementedError

    def owns_collection(self, fingerprint: dict[str, Any], connector_type: str) -> bool:
        """Whether this probe takes over collection from the unified engine."""
        return False

    async def collect(self, creds: ProbeCredentials) -> dict[str, Any]:
        """Pull inventory and push to Neo4j. Only called when ``owns_collection``."""
        raise NotImplementedError
