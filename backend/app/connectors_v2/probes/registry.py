"""Probe registry — the single ordered list of transport probes.

Both the scanner (identification) and :class:`UnifiedConnector` (collection)
iterate this same registry, so there is exactly one place that knows which
transports exist and in which order they are tried.
"""

from __future__ import annotations

from typing import Any

from app.connectors_v2.probes.base import Identity, Probe, ProbeCredentials
from app.connectors_v2.probes.fdm_api_probe import FdmApiProbe
from app.connectors_v2.probes.ssh_probe import SSHProbe


def get_probes() -> list[Probe]:
    """Ordered probes. SSH first (cheapest, broadest), then API/OAuth."""
    return [SSHProbe(), FdmApiProbe()]


def identify(creds: ProbeCredentials) -> Identity | None:
    """Run probes in order and return the first successful identification."""
    for probe in get_probes():
        if not probe.supports(creds):
            continue
        identity = probe.identify(creds)
        if identity and identity.is_identified():
            return identity
    return None


def select_collection_probe(
    fingerprint: dict[str, Any], connector_type: str
) -> Probe | None:
    """Return the probe that owns collection for this device, if any.

    When ``None``, the unified profile-driven engine performs collection.
    """
    for probe in get_probes():
        if probe.owns_collection(fingerprint, connector_type):
            return probe
    return None
