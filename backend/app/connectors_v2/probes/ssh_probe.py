"""SSH/CLI probe — Netmiko-based identification.

Identification runs ``show version`` over SSH and fingerprints the output
against the device profiles. Collection for SSH devices is performed by the
unified profile-driven engine in :class:`UnifiedConnector`, so this probe does
not own collection.
"""

from __future__ import annotations

import re

from app.connectors_v2.device_profile import DeviceProfile
from app.connectors_v2.fingerprint import fingerprint_from_cmd_output
from app.connectors_v2.probes.base import Identity, Probe, ProbeCredentials
from app.connectors_v2.transports import SSHTransport
from app.utils.logging import get_logger

logger = get_logger(__name__)


class SSHProbe(Probe):
    name = "ssh"
    transport = "ssh"

    def supports(self, creds: ProbeCredentials) -> bool:
        return creds.has_ssh and creds.transport_mode != "api"

    def identify(self, creds: ProbeCredentials) -> Identity | None:
        identity = Identity()
        try:
            ssh = SSHTransport(
                host=creds.host,
                port=creds.port,
                username=creds.username,
                password=creds.password,
                enable_password=creds.enable_password or creds.password,
                conn_timeout=10,
                cmd_timeout=15,
            )

            if not ssh.connect():
                return None

            try:
                out = ssh.run_command("show version")
            except Exception:
                out = ""

            if out:
                profiles = DeviceProfile.load_all()
                fp = fingerprint_from_cmd_output(out, profiles)
                for key in ("vendor", "os", "os_version", "hostname", "model"):
                    if fp.get(key):
                        setattr(identity, key, fp[key])

                m = re.search(r"(\S+)\s+uptime", out, re.IGNORECASE)
                if m:
                    identity.hostname = m.group(1)
                m = re.search(r"Version\s+([\d.]+)", out, re.IGNORECASE)
                if m:
                    identity.os_version = m.group(1)
                m = re.search(r"Processor board ID\s+(\S+)", out, re.IGNORECASE)
                if m:
                    identity.model = m.group(1)

            if not identity.hostname:
                try:
                    out = ssh.run_command("hostname")
                    if out and len(out.strip()) < 100:
                        identity.hostname = out.strip()
                except Exception:
                    pass

            ssh.disconnect()

        except Exception as exc:
            logger.debug("SSH identify error for %s: %s", creds.host, exc)
            return None

        if not identity.is_identified():
            return None

        identity.transport = "ssh"
        identity.source = "ssh_auth"
        return identity
