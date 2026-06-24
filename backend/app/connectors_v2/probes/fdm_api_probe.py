"""Cisco FDM/FTD API probe — OAuth2 identification & collection.

Centralizes ALL Cisco FTD handling that was previously dispersed across the
scanner (``_scan_api_fallback``) and ``UnifiedConnector`` (the ``_discover``
short-circuit, ``_should_use_legacy_ftd_sync``, ``_sync_legacy_cisco_ftd`` and
``_sync_ftd_via_api``).

FDM does **not** accept Basic auth — identification and collection both go
through an OAuth2 password-grant token (``POST /api/fdm/.../fdm/token``).
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any

from app.connectors_v2.lib.cisco_ftd import CiscoFTDConnector
from app.connectors_v2.probes.base import Identity, Probe, ProbeCredentials
from app.utils.logging import get_logger

logger = get_logger(__name__)


class FdmApiProbe(Probe):
    name = "fdm-api"
    transport = "api"

    def supports(self, creds: ProbeCredentials) -> bool:
        return creds.has_api and creds.transport_mode != "ssh"

    # ── identification ──────────────────────────────────────────
    def identify(self, creds: ProbeCredentials) -> Identity | None:
        helper = self._helper(creds)
        token = ""
        api_base = ""
        for base in helper.api_bases:
            try:
                token = helper._api_login(base)
                api_base = base
                break
            except Exception:
                continue

        if not token or not api_base:
            return None

        logger.info("FDM OAuth login OK pour %s", creds.host)
        identity = Identity(vendor="cisco", os="ftd", transport="api", source="api_fallback")

        # A 200 on any of these confirms FTD; enrich with facts when available.
        try:
            _path, payload = helper._api_get_first_success(
                api_base,
                token,
                [
                    "/devicesettings/default/deviceinformation",
                    "/devices/default/deviceversion",
                    "/object/networks?limit=1",
                ],
            )
            facts = helper._parse_api_device_facts(payload)
            identity.os_version = facts.get("os_version") or None
            identity.hostname = facts.get("hostname") or None
            identity.model = facts.get("model") or None
        except Exception:
            pass

        logger.info("FDM API identified: %s → cisco/ftd", creds.host)
        return identity

    # ── collection ──────────────────────────────────────────────
    def owns_collection(self, fingerprint: dict[str, Any], connector_type: str) -> bool:
        if connector_type == "cisco-ftd":
            return True
        return str(fingerprint.get("os") or "").strip().lower() == "ftd"

    async def collect(self, creds: ProbeCredentials) -> dict[str, Any]:
        api_result = await self._collect_via_api(creds)
        if api_result.get("status") == "ok" or creds.transport_mode == "api":
            api_result["role"] = "firewall"
            return api_result

        # API failed and SSH is permitted → legacy CLI fallback.
        ssh_result = await self._collect_via_ssh(creds)
        if ssh_result is not None:
            ssh_result["role"] = "firewall"
            return ssh_result

        api_result["role"] = "firewall"
        return api_result

    async def _collect_via_ssh(self, creds: ProbeCredentials) -> dict[str, Any] | None:
        try:
            legacy_result = await CiscoFTDConnector({
                "host": creds.host,
                "username": creds.username,
                "password": creds.password,
                "port": creds.port,
                "verify_ssl": creds.verify_ssl,
                "transport": "ssh",
            }).sync()
        except Exception as exc:
            logger.debug("FTD SSH fallback error for %s: %s", creds.host, exc)
            return None

        legacy_status = str(legacy_result.get("status", "error")).strip().lower()
        return {
            "status": "ok" if legacy_status == "synced" else "partial" if legacy_status == "partial" else "error",
            "vendor": legacy_result.get("vendor", "cisco-ftd"),
            "synced": legacy_result.get("synced", {}),
            "failed": legacy_result.get("failed", {}),
            "errors": legacy_result.get("errors", []),
        }

    async def _collect_via_api(self, creds: ProbeCredentials) -> dict[str, Any]:
        from app.connectors import display_name
        from app.connectors.base import SyncResult

        if not creds.has_api:
            return {
                "status": "error",
                "vendor": "cisco-ftd",
                "synced": {},
                "failed": {"devices": 1},
                "errors": ["FTD API credentials are not configured"],
            }

        helper = self._helper(creds)
        sync_result = SyncResult()
        token = ""
        api_base = ""
        last_error: str | None = None
        for base in helper.api_bases:
            try:
                token = await asyncio.to_thread(helper._api_login, base)
                api_base = base
                break
            except Exception as exc:
                last_error = str(exc)

        if not token or not api_base:
            return {
                "status": "error",
                "vendor": "cisco-ftd",
                "synced": {},
                "failed": {"devices": 1},
                "errors": [last_error or "FTD API login failed"],
            }

        facts = {
            "hostname": creds.host,
            "serial": hashlib.md5(creds.host.encode()).hexdigest()[:8].upper(),
            "model": "",
            "os_version": "",
        }
        try:
            _facts_path, facts_payload = await asyncio.to_thread(
                helper._api_get_first_success,
                api_base,
                token,
                [
                    "/devicesettings/default/deviceinformation",
                    "/devices/default/deviceversion",
                    "/devices/default",
                ],
            )
            parsed_facts = helper._parse_api_device_facts(facts_payload)
            facts.update({k: v for k, v in parsed_facts.items() if v})
        except Exception:
            pass

        interfaces: list[dict[str, str]] = []
        routes: list[dict[str, str]] = []
        rules: list[dict[str, str]] = []
        tunnels: list[dict[str, str]] = []

        try:
            _iface_path, iface_payload = await asyncio.to_thread(
                helper._api_get_first_success,
                api_base,
                token,
                [
                    "/devices/default/interfaces?limit=200",
                    "/devices/default/interfaces/physicalinterfaces?limit=200",
                    "/devices/default/interfaces/ethernetinterfaces?limit=200",
                    "/devices/default/physicalinterfaces?limit=200",
                ],
            )
            interfaces = helper._parse_api_interfaces(iface_payload)
        except Exception as exc:
            sync_result.record_failure("interfaces", f"api: {exc}")

        try:
            _route_path, route_payload = await asyncio.to_thread(
                helper._api_get_first_success,
                api_base,
                token,
                [
                    "/devices/default/routing/ipv4staticroutes?limit=200",
                    "/devices/default/routing/ipv4staticroutes",
                    "/devices/default/ipv4staticroutes?limit=200",
                    "/devices/default/ipv4staticroutes",
                ],
            )
            routes = helper._parse_api_routes(route_payload)
        except Exception as exc:
            if not helper._is_not_found_error(exc):
                sync_result.record_failure("routes", f"api: {exc}")

        try:
            policy_id = await asyncio.to_thread(helper._discover_access_policy_id, api_base, token)
            _rule_path, rule_payload = await asyncio.to_thread(
                helper._api_get_first_success,
                api_base,
                token,
                [
                    f"/policy/accesspolicies/{policy_id}/accessrules?limit=200",
                    "/policy/accesspolicies/default/accessrules?limit=200",
                ],
            )
            rules = helper._parse_api_rules(rule_payload)
        except Exception as exc:
            sync_result.record_failure("rules", f"api: {exc}")

        try:
            _vpn_path, vpn_payload = await asyncio.to_thread(
                helper._api_get_first_success,
                api_base,
                token,
                [
                    "/devices/default/vpn/s2svpntunnels?limit=200",
                    "/devices/default/vpn/s2svpntunnels",
                ],
            )
            tunnels = helper._parse_api_vpn_tunnels(vpn_payload)
        except Exception as exc:
            if not helper._is_not_found_error(exc):
                sync_result.record_failure("vpn_tunnels", f"api: {exc}")

        hostname = facts["hostname"] or creds.host
        serial = facts["serial"] or hashlib.md5(creds.host.encode()).hexdigest()[:8].upper()
        device_id = f"FTD-{serial}"
        device_dn = display_name.device(display_name.VENDOR_CISCO, display_name.FUNCTION_FIREWALL, hostname)

        try:
            await helper._merge_inventory(
                sync_result,
                hostname,
                device_id,
                device_dn,
                facts.get("model", ""),
                facts.get("os_version", ""),
                interfaces,
                routes,
                rules,
                tunnels,
            )
        except Exception as exc:
            sync_result.record_failure("devices", f"api: {exc}")

        sync_result.finalise()
        legacy_status = sync_result.status
        return {
            "status": "ok" if legacy_status == "synced" else "partial" if legacy_status == "partial" else "error",
            "vendor": "cisco-ftd",
            "hostname": hostname,
            "device_id": device_id,
            "display_name": device_dn,
            "synced": sync_result.synced,
            "failed": sync_result.failed,
            "errors": sync_result.errors,
        }

    @staticmethod
    def _helper(creds: ProbeCredentials) -> CiscoFTDConnector:
        return CiscoFTDConnector({
            "host": creds.host,
            "username": creds.api_username,
            "password": creds.api_password,
            "port": creds.api_port,
            "verify_ssl": creds.verify_ssl,
            "transport": "api",
        })
