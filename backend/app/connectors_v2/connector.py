from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import os
import re
import time
from typing import Any

from app.connectors_v2.device_profile import DeviceProfile, fingerprint_device
from app.connectors_v2.parsers import TextFSMParser, LLMParser
from app.connectors_v2.transports import SSHTransport, APITransport
from app.graph.neo4j_client import neo4j_client
from app.utils.logging import get_logger

logger = get_logger(__name__)

_FINGERPRINT_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_FINGERPRINT_TTL = int(os.environ.get("FINGERPRINT_TTL_SECONDS", "3600"))
_CIRCUIT_BREAKER: dict[str, float] = {}
_CIRCUIT_RESET = int(os.environ.get("CIRCUIT_BREAKER_RESET_SECONDS", "120"))


class UnifiedConnector:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.connector_type = str(config.get("_connector_type", config.get("connector_type", ""))).strip().lower()
        self.host = config.get("host", "")
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        self.api_username = config.get("api_username", config.get("username", ""))
        self.api_password = config.get("api_password", config.get("password", ""))
        self.port = int(config.get("port", 22))
        self.api_port = int(config.get("api_port", 443))
        self.api_key = config.get("api_key", "")
        self.api_token = config.get("api_token", "")
        self.verify_ssl = bool(config.get("verify_ssl", False))
        self.transport_mode = config.get("transport", "auto")

        self._fingerprint: dict[str, Any] = {}
        self._profile: DeviceProfile | None = None
        self._transport: SSHTransport | APITransport | None = None
        self._textfsm = TextFSMParser()
        self._llm = LLMParser()

    # ── circuit breaker ──────────────────────────────────────────
    def _is_circuit_open(self) -> bool:
        opened = _CIRCUIT_BREAKER.get(self.host)
        if opened and time.time() - opened < _CIRCUIT_RESET:
            return True
        if opened:
            del _CIRCUIT_BREAKER[self.host]
        return False

    def _open_circuit(self) -> None:
        _CIRCUIT_BREAKER[self.host] = time.time()
        logger.warning("Circuit breaker opened for %s (%ss)", self.host, _CIRCUIT_RESET)

    # ── fingerprint cache ────────────────────────────────────────
    def _get_cached_fingerprint(self) -> dict[str, Any] | None:
        entry = _FINGERPRINT_CACHE.get(self.host)
        if entry and time.time() - entry[0] < _FINGERPRINT_TTL:
            return entry[1]
        return None

    def _set_fingerprint_cache(self, fp: dict[str, Any]) -> None:
        _FINGERPRINT_CACHE[self.host] = (time.time(), fp)

    # ── sync ─────────────────────────────────────────────────────
    async def sync(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "status": "ok",
            "vendor": "",
            "hostname": "",
            "device_id": "",
            "display_name": "",
            "synced": {},
            "failed": {},
            "errors": [],
        }

        if self._is_circuit_open():
            result["status"] = "error"
            result["errors"].append(f"Circuit breaker open for {self.host}")
            return result

        try:
            fp = self._get_cached_fingerprint()
            if not fp:
                fp = await asyncio.to_thread(self._discover)
                self._set_fingerprint_cache(fp)
            self._fingerprint = fp
            result["vendor"] = fp.get("vendor", "") or ""
            result["device_fingerprint"] = fp

            logger.info("Device %s fingerprint: vendor=%s os=%s transport=%s",
                        self.host, fp.get("vendor"), fp.get("os"), fp.get("transport"))

            profile = DeviceProfile.find_match(fp, DeviceProfile.load_all())
            if profile:
                self._profile = profile
                logger.info("Matched profile: %s", profile.name)

                if self._should_use_legacy_ftd_sync(fp) or self.transport_mode == "api":
                    return await self._sync_legacy_cisco_ftd(result)

            if not fp.get("vendor") and self._llm.is_available():
                cmd_out = await asyncio.to_thread(self._try_discovery_commands)
                if cmd_out:
                    llm_commands = await asyncio.to_thread(self._llm.discover_commands, cmd_out, fp)
                    if llm_commands:
                        fp["llm_commands"] = llm_commands

            def _connect_and_collect():
                if not self._connect():
                    return None
                return self._collect_all()

            sync_data = await asyncio.to_thread(_connect_and_collect)
            if sync_data is None:
                self._open_circuit()
                result["status"] = "error"
                result["errors"].append("No transport could connect to device")
                return result
            result.update(sync_data)

            # Infer device role from available context
            from app.connectors_v2.device_profile import infer_device_role
            role = infer_device_role(
                vendor=fp.get("vendor", ""),
                os_name=fp.get("os", ""),
                model=result.get("model", fp.get("model")),
                interface_count=len(result.get("interfaces", [])),
                has_routing_protocols=bool(result.get("routes") or result.get("bgp_peers")),
                profile_role=self._profile.device_role if self._profile else "",
            )
            result["role"] = role
            fp["role"] = role
            logger.info("Device %s inferred role: %s", self.host, role)

            await self._push_to_neo4j(result)
            await self._infer_topology()

            return result

        except Exception as e:
            logger.error("Sync failed for %s: %s", self.host, e)
            self._open_circuit()
            result["status"] = "error"
            result["errors"].append(str(e))
            return result
        finally:
            if self._transport:
                try:
                    await asyncio.to_thread(self._transport.disconnect)
                except Exception:
                    pass

    def _should_use_legacy_ftd_sync(self, fp: dict[str, Any]) -> bool:
        if self.connector_type == "cisco-ftd":
            return True
        return str(fp.get("os") or "").strip().lower() == "ftd"

    async def _sync_legacy_cisco_ftd(self, result: dict[str, Any]) -> dict[str, Any]:
        api_result = await self._sync_ftd_via_api()
        if api_result.get("status") == "ok" or self.transport_mode == "api":
            result.update(api_result)
            result["role"] = "firewall"
            await self._infer_topology()
            return result

        from app.connectors.cisco_ftd import CiscoFTDConnector

        legacy_result = await CiscoFTDConnector({
            "host": self.host,
            "username": self.username,
            "password": self.password,
            "port": self.port,
            "verify_ssl": self.verify_ssl,
            "transport": "ssh",
        }).sync()
        legacy_status = str(legacy_result.get("status", "error")).strip().lower()
        result.update({
            "status": "ok" if legacy_status == "synced" else "partial" if legacy_status == "partial" else "error",
            "vendor": legacy_result.get("vendor", result.get("vendor", "cisco-ftd")),
            "synced": legacy_result.get("synced", {}),
            "failed": legacy_result.get("failed", {}),
            "errors": legacy_result.get("errors", []),
        })
        result["role"] = "firewall"
        await self._infer_topology()
        return result

    async def _sync_ftd_via_api(self) -> dict[str, Any]:
        from app.connectors import display_name
        from app.connectors.base import SyncResult
        from app.connectors.cisco_ftd import CiscoFTDConnector

        if not (self.api_username and self.api_password):
            return {
                "status": "error",
                "vendor": "cisco-ftd",
                "synced": {},
                "failed": {"devices": 1},
                "errors": ["FTD API credentials are not configured"],
            }

        helper = CiscoFTDConnector({
            "host": self.host,
            "username": self.api_username,
            "password": self.api_password,
            "port": self.api_port,
            "verify_ssl": self.verify_ssl,
            "transport": "api",
        })

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
            "hostname": self.host,
            "serial": hashlib.md5(self.host.encode()).hexdigest()[:8].upper(),
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

        hostname = facts["hostname"] or self.host
        serial = facts["serial"] or hashlib.md5(self.host.encode()).hexdigest()[:8].upper()
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

    # ── discovery ────────────────────────────────────────────────
    def _discover(self) -> dict[str, Any]:
        if self.connector_type == "cisco-ftd" and self.transport_mode != "ssh" and self.api_username and self.api_password:
            return {
                "vendor": "cisco",
                "os": "ftd",
                "os_version": None,
                "hostname": None,
                "model": None,
                "transport": "api",
                "api_version": "latest",
                "source": "config_connector_type",
            }

        fp = fingerprint_device(
            host=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            api_username=self.api_username,
            api_password=self.api_password,
        )
        if self.transport_mode in ("ssh", "api") and fp.get("transport") != self.transport_mode:
            fp["transport"] = self.transport_mode
            fp["source"] = f"config_override_{self.transport_mode}"
        return fp

    def _try_discovery_commands(self) -> str:
        if not isinstance(self._transport, SSHTransport):
            return ""
        try:
            for cmd in ["help", "?", "show ?"]:
                try:
                    out = self._transport.send_command(cmd, timeout=10)
                    if out and len(out) > 50:
                        return out[:6000]
                except Exception:
                    continue
        except Exception:
            pass
        return ""

    # ── connect ──────────────────────────────────────────────────
    def _connect(self) -> bool:
        profile = self._profile
        transport_candidates: list[dict[str, Any]] = []

        if profile:
            transport_candidates = list(profile.transports)

        if not transport_candidates:
            transport_candidates = [{"type": "ssh", "priority": 10, "device_type": "cisco_ios"}]

        if self.transport_mode == "api":
            transport_candidates = [t for t in transport_candidates if t.get("type") == "api"]
        elif self.transport_mode == "ssh":
            transport_candidates = [t for t in transport_candidates if t.get("type") == "ssh"]

        transport_candidates.sort(key=lambda x: -x.get("priority", 0))

        last_error: str | None = None
        for tc in transport_candidates:
            ttype = tc.get("type", "ssh")
            try:
                if ttype == "api":
                    t = APITransport(
                        host=self.host,
                        port=self.api_port,
                        username=self.api_username,
                        password=self.api_password,
                        api_key=self.api_key,
                        api_token=self.api_token,
                        verify_ssl=self.verify_ssl,
                        base_path=tc.get("api_base", "/api/fdm/latest"),
                    )
                    if t.connect():
                        self._transport = t
                        return True
                elif ttype == "ssh":
                    t = SSHTransport(
                        host=self.host,
                        port=self.port,
                        username=self.username,
                        password=self.password,
                        enable_password=self.config.get("enable_password", self.password),
                        device_type=tc.get("device_type", "cisco_ios"),
                    )
                    if t.connect():
                        self._transport = t
                        return True
            except Exception as e:
                last_error = str(e)
                logger.debug("Transport %s failed for %s: %s", ttype, self.host, e)
                continue

        if last_error:
            logger.warning("All transports failed for %s: %s", self.host, last_error)
        return False

    # ── collect ──────────────────────────────────────────────────
    def _collect_all(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "status": "ok",
            "hostname": "",
            "serial": "",
            "model": "",
            "os_version": "",
            "interfaces": [],
            "routes": [],
            "vlans": [],
            "rules": [],
            "bgp_peers": [],
            "mac_table": [],
            "topology_neighbors": [],
            "redundancy": {},
            "acl_bindings": [],
            "access_lists": [],
            "services": [],
            "errors": [],
        }

        profile = self._profile
        commands_map: dict[str, str] = {}
        command_groups: list[str] = ["system"]

        if profile:
            commands_map = dict(profile.commands)
            command_groups = profile.get_all_command_groups()
        else:
            commands_map = {"show_version": "show version", "hostname": "hostname"}

        for group in command_groups:
            if group == "all":
                continue
            cmds = profile.get_commands_for_group(group) if profile else [commands_map.get("show_version", "show version")]
            for cmd_name in cmds if isinstance(cmds, list) else [cmds]:
                command_name = cmd_name if isinstance(cmd_name, str) else ""
                if not command_name:
                    continue
                try:
                    raw_out = self._run_device_command(command_name)
                except Exception as e:
                    result["errors"].append(f"{command_name}: {e}")
                    continue

                if not raw_out.strip():
                    continue

                parsed = self._parse_output(command_name, raw_out)
                iso = command_name.lower()
                if "version" in iso or "system" in iso:
                    self._extract_system_info(raw_out, result)
                elif "interface" in iso or "int_brief" in iso:
                    existing_interfaces = list(result.get("interfaces", []))
                    if self._is_ip_interface_brief_command(command_name):
                        result["interfaces"] = self._parse_ip_int_brief(raw_out, existing_interfaces)
                    else:
                        result["interfaces"] = self._merge_interfaces(
                            existing_interfaces,
                            self._normalize_interfaces(parsed, raw_out),
                        )
                elif "route" in iso:
                    result["routes"] = self._normalize_routes(parsed, raw_out)
                elif "vlan" in iso:
                    result["vlans"] = self._normalize_vlans(parsed, raw_out)
                elif "bgp" in iso:
                    result["bgp_peers"] = self._normalize_bgp(parsed, raw_out)
                elif "mac" in iso or "address-table" in iso:
                    result["mac_table"] = parsed
                elif "cdp" in iso or "lldp" in iso:
                    protocol = "cdp" if "cdp" in iso else "lldp"
                    existing = result.get("topology_neighbors", [])
                    result["topology_neighbors"] = existing + self._normalize_neighbors(parsed, protocol)
                elif "standby" in iso or "hsrp" in iso:
                    hsrp_data = self._normalize_redundancy(parsed, "hsrp", raw_out)
                    result["redundancy"] = {**result.get("redundancy", {}), **hsrp_data}
                elif "vrrp" in iso:
                    vrrp_data = self._normalize_redundancy(parsed, "vrrp", raw_out)
                    result["redundancy"] = {**result.get("redundancy", {}), **vrrp_data}
                elif "etherchannel" in iso or "port-channel" in iso:
                    ec_data = self._normalize_etherchannel(parsed, raw_out)
                    result["redundancy"] = {**result.get("redundancy", {}), **ec_data}
                elif "redundancy" in iso and "standby" not in iso and "vrrp" not in iso:
                    gen_data = self._normalize_redundancy_general(parsed, raw_out)
                    result["redundancy"] = {**result.get("redundancy", {}), **gen_data}
                elif "ip interface" in iso and "brief" not in iso:
                    result["acl_bindings"] = self._parse_acl_bindings(raw_out)
                elif "access-list" in iso or "access" in iso and "list" in iso:
                    result["access_lists"] = self._normalize_access_lists(parsed, raw_out)
                elif "http" in iso and ("server" in iso or "status" in iso):
                    result["services"] = self._normalize_http_service(raw_out, parsed)
                elif "network" in iso:
                    self._parse_ftd_network(raw_out, result)
                elif "manager" in iso:
                    pass

        if not result["hostname"]:
            result["hostname"] = self.host
        if not result["serial"]:
            result["serial"] = hashlib.md5(self.host.encode()).hexdigest()[:8].upper()
        return result

    def _run_device_command(self, command: str) -> str:
        if isinstance(self._transport, SSHTransport):
            return self._transport.send_command(command, timeout=30)
        elif isinstance(self._transport, APITransport):
            try:
                data = self._transport.get(command.split("?")[0])
                import json
                return json.dumps(data, indent=2)
            except Exception:
                return ""
        return ""

    def _parse_output(self, command: str, raw_output: str) -> list[dict[str, str]]:
        profile = self._profile
        os_name = "cisco_ios"
        if profile:
            parser_type = profile.parsers.get(command, "textfsm")
        else:
            parser_type = "textfsm"
        if self._fingerprint.get("os"):
            os_name = str(self._fingerprint["os"])

        if parser_type == "llm" and self._llm.is_available():
            try:
                return self._llm.parse_output(command, raw_output, self._fingerprint)
            except Exception:
                pass

        parsed = self._textfsm.parse(command, raw_output, os_name=os_name)
        if (not parsed or parsed == [{"raw": raw_output}]) and self._llm.is_available():
            try:
                llm_result = self._llm.parse_output(command, raw_output, self._fingerprint)
                if llm_result:
                    return llm_result
            except Exception:
                pass
        return parsed

    # ── FTD network parser ──────────────────────────────────────
    def _parse_ftd_network(self, output: str, result: dict[str, Any]) -> None:
        hm = re.search(r"Hostname\s*:\s*(\S+)", output, re.IGNORECASE)
        if hm:
            result["hostname"] = hm.group(1)
        iface_name = None
        for line in output.splitlines():
            m = re.match(r"=+\s*\[\s*(.+?)\s*]\s*=*\s*$", line)
            if m:
                iface_name = m.group(1).strip()
                continue
            if iface_name:
                im = re.match(r"Address\s*:\s*(\S+)", line)
                if im:
                    ip = im.group(1)
                    if ":" not in ip and ip.count(".") == 3:
                        result.setdefault("interfaces", []).append({
                            "name": iface_name, "status": "up", "ip": ip, "mask": "",
                        })

    # ── system info extractors ──────────────────────────────────
    def _normalize_neighbors(self, parsed: list[dict], protocol: str) -> list[dict]:
        """Normalize CDP/LLDP neighbor data into a standard format."""
        neighbors: list[dict] = []
        for entry in parsed if isinstance(parsed, list) else []:
            if not entry.get("neighbor_name"):
                continue
            neighbors.append({
                "hostname": entry.get("neighbor_name", ""),
                "local_interface": entry.get("local_interface", ""),
                "neighbor_interface": entry.get("neighbor_interface", ""),
                "platform": entry.get("platform", ""),
                "capabilities": entry.get("capabilities", ""),
                "management_ip": entry.get("mgmt_address", ""),
                "protocol": protocol,
            })
        return neighbors

    def _is_ip_interface_brief_command(self, command: str) -> bool:
        cmd = command.strip().lower()
        return bool(re.search(r"\bshow\s+ip\s+int(?:erface)?\s+brief\b", cmd))

    def _merge_interfaces(
        self,
        existing: list[dict[str, str]],
        new_items: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        merged: dict[str, dict[str, str]] = {}
        for iface in [*existing, *new_items]:
            name = str(iface.get("name", "")).strip()
            if not name:
                continue
            current = merged.setdefault(name, {
                "name": name,
                "status": "unknown",
                "ip": "",
                "mask": "",
            })
            status = str(iface.get("status", "")).strip()
            if status and status != "unknown":
                current["status"] = status
            for field in ("ip", "mask"):
                value = str(iface.get(field, "")).strip()
                if value:
                    current[field] = value
        return list(merged.values())

    def _parse_ip_int_brief(self, raw: str, existing: list[dict[str, str]]) -> list[dict[str, str]]:
        seen = {i["name"] for i in existing}
        for line in raw.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[0] not in ("Interface",):
                m = re.match(r"(\S+)", parts[0])
                if m:
                    name = m.group(1)
                    ip = parts[1] if len(parts) > 1 and parts[1] != "unassigned" else ""
                    status = "up" if len(parts) > 4 and "up" in parts[4].lower() else "down"
                    if name not in seen and ip:
                        seen.add(name)
                        existing.append({"name": name, "status": status, "ip": ip, "mask": ""})
        return existing

    def _extract_system_info(self, output: str, result: dict[str, Any]) -> None:
        if not result["hostname"]:
            for pat in [r"(\S+)\s+uptime", r"hostname\s+(\S+)", r"System Name\s*\.+\s*(\S+)", r"Hostname\s*:\s*(\S+)"]:
                m = re.search(pat, output, re.IGNORECASE)
                if m: result["hostname"] = m.group(1); break
        if not result["serial"]:
            for pat in [r"Processor board ID\s+(\S+)", r"Serial\s*(?:Number)?\s*:\s*(\S+)"]:
                m = re.search(pat, output, re.IGNORECASE)
                if m: result["serial"] = m.group(1); break
        if not result["model"]:
            m = re.search(r"Model\s*(?:number)?\s*:\s*(.+?)(?:\s+Version|\s*$)", output, re.IGNORECASE)
            if m: result["model"] = m.group(1).strip()
        if not result["os_version"]:
            m = re.search(r"Version\s+([\d.]+)", output, re.IGNORECASE)
            if m: result["os_version"] = m.group(1)

    # ── interface parser ────────────────────────────────────────
    def _normalize_interfaces(self, parsed: list[dict[str, str]], raw: str) -> list[dict[str, Any]]:
        if parsed and parsed[0].get("raw"):
            return self._parse_interfaces_raw(raw)
        normalized, seen = [], set()
        for iface in parsed:
            name = iface.get("interface", iface.get("name", iface.get("intf", "")))
            if not name or name in seen:
                continue
            seen.add(name)
            entry: dict[str, Any] = {
                "name": name,
                "status": iface.get("status", iface.get("link", "unknown")),
                "ip": iface.get("ip_address", iface.get("ipaddr", iface.get("ip", ""))),
                "mask": iface.get("mask", iface.get("subnet", "")),
            }
            # Extract error counters and metrics if available
            for metric_key in ["input_rate", "output_rate", "input_errors",
                               "output_errors", "crc", "runts", "giants", "frame",
                               "input_packets", "output_packets"]:
                val = iface.get(metric_key, iface.get(metric_key.upper(), ""))
                if val not in (None, "", "0"):
                    try:
                        entry[metric_key] = int(val)
                    except (ValueError, TypeError):
                        entry[metric_key] = val
            normalized.append(entry)
        if not normalized:
            return self._parse_interfaces_raw(raw)
        return normalized

    def _parse_interfaces_raw(self, raw: str) -> list[dict[str, str]]:
        interfaces, current, seen = [], {}, set()
        for line in raw.splitlines():
            m = re.match(r"^(\S+)\s+is\s+(up|down|administratively down)", line.strip(), re.IGNORECASE)
            if m:
                if current.get("name") and current["name"] not in seen:
                    interfaces.append(current); seen.add(current["name"])
                current = {"name": m.group(1), "status": m.group(2), "ip": "", "mask": ""}; continue
            if current:
                for pat in [r"Internet address is (\S+)", r"inet\s+(\S+)"]:
                    ipm = re.search(pat, line)
                    if ipm:
                        parts = ipm.group(1).split("/")
                        current["ip"] = parts[0]
                        if len(parts) > 1: current["mask"] = parts[1]
        if current.get("name") and current["name"] not in seen:
            interfaces.append(current)
        return interfaces

    def _normalize_routes(self, parsed: list[dict[str, str]], raw: str) -> list[dict[str, str]]:
        if parsed and parsed[0].get("raw"):
            routes, seen = [], set()
            for line in raw.splitlines():
                m = re.search(r"(\d+\.\d+\.\d+\.\d+/\d+)", line)
                if m and m.group(1) not in seen:
                    routes.append({"network": m.group(1)}); seen.add(m.group(1))
            return routes
        return [{"network": r.get("network", r.get("prefix", ""))} for r in parsed if r.get("network") or r.get("prefix")]

    def _normalize_vlans(self, parsed: list[dict[str, str]], raw: str) -> list[dict[str, Any]]:
        if parsed and parsed[0].get("raw"):
            vlans, seen = [], set()
            for line in raw.splitlines():
                m = re.match(r"^\s*(\d+)\s+(\S+)", line.strip())
                if m and m.group(1).isdigit() and m.group(1) not in seen:
                    vlans.append({"vlan_id": m.group(1), "name": m.group(2), "interfaces": []}); seen.add(m.group(1))
            return vlans
        result = []
        seen_ids = set()
        for v in parsed:
            vid = v.get("vlan_id", v.get("id", ""))
            if not vid or vid in seen_ids:
                continue
            seen_ids.add(vid)
            raw_ports = v.get("interfaces", v.get("ports", ""))
            ports = []
            if isinstance(raw_ports, list):
                ports = [p.strip() for p in raw_ports if p.strip()]
            elif isinstance(raw_ports, str) and raw_ports.strip():
                ports = [x.strip() for x in raw_ports.replace(",", " ").split() if x.strip()]
            result.append({
                "vlan_id": vid,
                "name": v.get("name", v.get("vlan_name", "")),
                "interfaces": ports,
            })
        return result

    def _normalize_bgp(self, parsed: list[dict[str, str]], raw: str) -> list[dict[str, str]]:
        if parsed and parsed[0].get("raw"):
            peers, seen = [], set()
            for line in raw.splitlines():
                m = re.match(r"^(\d+\.\d+\.\d+\.\d+)\s+", line.strip())
                if m and m.group(1) not in seen:
                    peers.append({"neighbor": m.group(1)}); seen.add(m.group(1))
            return peers
        return [{"neighbor": p.get("neighbor", p.get("bgp_peer", ""))} for p in parsed if p.get("neighbor") or p.get("bgp_peer")]

    # ── Redundancy normalization (HSRP, VRRP, EtherChannel, Stack) ──
    def _normalize_redundancy(self, parsed: list[dict], protocol: str, raw: str) -> dict[str, Any]:
        """Normalize HSRP/VRRP standby data into a structured format."""
        result: dict[str, Any] = {
            "protocol": protocol,
            "groups": [],
            "has_redundancy": False,
        }
        if parsed and not parsed[0].get("raw"):
            for entry in parsed:
                group_id = entry.get("group", entry.get("grp_num", ""))
                virtual_ip = entry.get("virtual_ip", entry.get("ip", ""))
                state = entry.get("state", "").lower()
                priority = entry.get("priority", "")
                active_router = entry.get("active_router", "")
                standby_router = entry.get("standby_router", "")
                interface = entry.get("interface", entry.get("iface", ""))
                if group_id:
                    result["groups"].append({
                        "group": group_id,
                        "virtual_ip": virtual_ip,
                        "state": state,
                        "priority": priority,
                        "active_router": active_router,
                        "standby_router": standby_router,
                        "interface": interface,
                    })
                    if state == "active" and standby_router and standby_router not in ("unknown", "this"):
                        result["has_redundancy"] = True
        if not result["groups"]:
            # Fallback: parse raw text
            for line in raw.splitlines():
                m = re.search(r"Group\s+(\d+).*state\s+(Active|Standby|Init|Listen)", line, re.IGNORECASE)
                if m:
                    result["groups"].append({"group": m.group(1), "state": m.group(2).lower()})
                    result["has_redundancy"] = True
        return result

    def _normalize_etherchannel(self, parsed: list[dict], raw: str) -> dict[str, Any]:
        """Normalize EtherChannel/port-channel data."""
        result: dict[str, Any] = {
            "protocol": "etherchannel",
            "channels": [],
            "has_redundancy": False,
        }
        if parsed and not parsed[0].get("raw"):
            for entry in parsed:
                channel = entry.get("channel", entry.get("group", entry.get("port_channel", "")))
                ports = entry.get("ports", entry.get("member_interfaces", ""))
                protocol = entry.get("protocol", entry.get("mode", ""))
                status = entry.get("status", entry.get("state", ""))
                if channel:
                    result["channels"].append({
                        "channel": channel,
                        "ports": ports,
                        "protocol": protocol,
                        "status": status,
                    })
                    if len(ports.split(",")) if ports else 0 >= 2:
                        result["has_redundancy"] = True
        return result

    def _normalize_redundancy_general(self, parsed: list[dict], raw: str) -> dict[str, Any]:
        """Normalize general 'show redundancy' output."""
        result: dict[str, Any] = {
            "protocol": "redundancy",
            "has_redundancy": False,
            "details": {},
        }
        # Parse key-value pairs from show redundancy
        for line in raw.splitlines():
            m = re.search(r"System Redundancy Protocol\s*=\s*(\S+)", line, re.IGNORECASE)
            if m:
                result["details"]["protocol"] = m.group(1)
            m = re.search(r"Redundancy.*State\s*=\s*(\S+)", line, re.IGNORECASE)
            if m:
                result["details"]["state"] = m.group(1).lower()
                result["has_redundancy"] = m.group(1).lower() != "none"
        return result

    # ── ACL parsing ──────────────────────────────────────────────
    def _parse_acl_bindings(self, raw: str) -> list[dict[str, str]]:
        """Parse 'show ip interface' output to extract ACL bindings per interface."""
        bindings: list[dict[str, str]] = []
        current_iface = ""
        for line in raw.splitlines():
            m = re.match(r"^(\S+)\s+is", line.strip())
            if m:
                current_iface = m.group(1)
            m_in = re.search(r"Inbound\s+access list\s+is\s+(.+)$", line, re.IGNORECASE)
            if m_in and current_iface:
                acl_name = m_in.group(1).strip()
                if acl_name.lower() != "not set":
                    bindings.append({"interface": current_iface, "direction": "in", "acl": acl_name})
            m_out = re.search(r"Outgoing\s+access list\s+is\s+(.+)$", line, re.IGNORECASE)
            if m_out and current_iface:
                acl_name = m_out.group(1).strip()
                if acl_name.lower() != "not set":
                    bindings.append({"interface": current_iface, "direction": "out", "acl": acl_name})
        return bindings

    def _normalize_access_lists(self, parsed: list[dict], raw: str) -> list[dict[str, Any]]:
        """Normalize 'show access-list' output."""
        acls: list[dict[str, Any]] = []
        if parsed and not parsed[0].get("raw"):
            for entry in parsed:
                acl_id = entry.get("acl_id", entry.get("id", entry.get("number", "")))
                acl_name = entry.get("name", acl_id)
                acl_type = entry.get("type", "ip")
                entries = entry.get("entries", entry.get("access_control_entries", []))
                if acl_id:
                    acls.append({"id": acl_id, "name": acl_name, "type": acl_type, "entries": entries})
        if not acls:
            # Fallback: parse raw output
            current_acl = None
            for line in raw.splitlines():
                m = re.match(r"^(?:Standard|Extended)\s+IP\s+access\s+list\s+(.+)$", line, re.IGNORECASE)
                if m:
                    current_acl = {"id": m.group(1).strip(), "name": m.group(1).strip(), "type": "ip", "entries": []}
                    acls.append(current_acl)
                elif current_acl and line.strip() and not line.startswith(" "):
                    current_acl = None
        return acls

    # ── Services detection ──────────────────────────────────────
    def _normalize_http_service(self, raw: str, parsed: list[dict]) -> list[dict[str, Any]]:
        """Parse 'show ip http server status' to extract HTTP service info."""
        services: list[dict[str, Any]] = []
        enabled = False
        port = 80
        if parsed and not parsed[0].get("raw"):
            entry = parsed[0] if parsed else {}
            enabled = entry.get("status", "").lower() == "enabled" if entry.get("status") else False
            port = int(entry.get("port", 80)) if entry.get("port") else 80
        else:
            m = re.search(r"HTTP server status:\s*(\S+)", raw, re.IGNORECASE)
            if m:
                enabled = m.group(1).lower() == "enabled"
            m = re.search(r"HTTP server port:\s*(\d+)", raw, re.IGNORECASE)
            if m:
                port = int(m.group(1))
        services.append({
            "name": "http",
            "protocol": "tcp",
            "port": port,
            "enabled": enabled,
            "source": "show ip http server status",
        })
        if enabled:
            logger.info("Service detected: HTTP (port %d) on %s", port, self.host)
        return services

    # ── Neo4j push (upsert par hostname+ip) ──────────────────────
    async def _push_to_neo4j(self, data: dict[str, Any]) -> None:
        hostname = data.get("hostname", self.host)
        serial = data.get("serial", hostname)
        device_id = f"DEV-{serial}"
        vendor = data.get("vendor", self._fingerprint.get("vendor", "unknown"))
        role = data.get("role", self._fingerprint.get("os", "unknown"))
        ip = self.host
        display_name = f"{hostname} ({vendor}/{role})"

        try:
            existing = await self._find_device_by_hostname_ip(hostname, ip)
            if existing:
                device_id = existing["id"]
            redundancy = data.get("redundancy", {})
            has_redundancy = redundancy.get("has_redundancy", False) if isinstance(redundancy, dict) else False
            redundancy_protocol = ""
            if isinstance(redundancy, dict):
                if redundancy.get("groups"):
                    redundancy_protocol = f"hsrp_{len(redundancy['groups'])}_groups"
                elif redundancy.get("channels"):
                    redundancy_protocol = f"etherchannel_{len(redundancy['channels'])}_channels"
                elif redundancy.get("details", {}).get("protocol"):
                    redundancy_protocol = redundancy["details"]["protocol"]
            elif redundancy:
                redundancy_protocol = "unknown"

            # Serialize ACL bindings for Neo4j storage
            acl_bindings = data.get("acl_bindings", [])
            acl_bindings_json = json.dumps(acl_bindings) if acl_bindings else ""

            # Serialize services for Neo4j storage
            services = data.get("services", [])
            services_json = json.dumps(services) if services else ""

            await neo4j_client.merge_node("Device", device_id, {
                "id": device_id,
                "type": role,
                "vendor": vendor,
                "hostname": hostname,
                "model": data.get("model", ""),
                "os_version": data.get("os_version", ""),
                "serial": serial,
                "ip": ip,
                "role": role,
                "has_redundancy": has_redundancy,
                "redundancy_protocol": redundancy_protocol,
                "acl_bindings": acl_bindings_json,
                "services": services_json,
                "display_name": display_name,
            })
            data["device_id"] = device_id
            data["display_name"] = display_name
        except Exception as e:
            data.setdefault("errors", []).append(f"neo4j device: {e}")

        # Build VLAN-to-interfaces index
        vlan_ifaces: dict[str, list[str]] = {}
        for vlan in data.get("vlans", []):
            vid = vlan.get("vlan_id", "")
            ifaces = vlan.get("interfaces", [])
            if vid and ifaces:
                for ifname in ifaces:
                    if ifname not in vlan_ifaces:
                        vlan_ifaces[ifname] = []
                    vlan_ifaces[ifname].append(vid)

        seen_ifaces: set[str] = set()
        acl_index: dict[str, dict[str, str]] = {}
        for b in data.get("acl_bindings", []):
            ifname = b.get("interface", "")
            direction = b.get("direction", "")
            acl_name = b.get("acl", "")
            if ifname:
                if ifname not in acl_index:
                    acl_index[ifname] = {}
                acl_index[ifname][direction] = acl_name

        for iface in data.get("interfaces", []):
            ifname = iface.get("name", "")
            if not ifname or ifname in seen_ifaces:
                continue
            seen_ifaces.add(ifname)
            iface_id = f"IF-{serial}-{ifname}"
            acl_props = {}
            if ifname in acl_index:
                if "in" in acl_index[ifname]:
                    acl_props["acl_in"] = acl_index[ifname]["in"]
                if "out" in acl_index[ifname]:
                    acl_props["acl_out"] = acl_index[ifname]["out"]
            vlan_info = {}
            if ifname in vlan_ifaces:
                vlan_info["vlans"] = ",".join(vlan_ifaces[ifname])
            # Interface health metrics
            metrics = {}
            for m_key in ["input_rate", "output_rate", "input_errors",
                          "output_errors", "crc", "runts", "giants", "frame"]:
                val = iface.get(m_key)
                if val not in (None, "", 0):
                    metrics[m_key] = int(val) if isinstance(val, (int, float, str)) and str(val).isdigit() else val
            try:
                await neo4j_client.merge_node("Interface", iface_id, {
                    "id": iface_id, "name": ifname,
                    "status": iface.get("status", "unknown"),
                    "ip": iface.get("ip", ""), "mask": iface.get("mask", ""),
                    "display_name": f"{ifname} ({hostname})",
                    **acl_props,
                    **vlan_info,
                    **metrics,
                })
                await neo4j_client.create_relationship("Device", device_id, "HAS_INTERFACE", "Interface", iface_id)
            except Exception:
                pass

        seen_routes: set[str] = set()
        for route in data.get("routes", []):
            network = route.get("network", "")
            if not network or network in seen_routes:
                continue
            seen_routes.add(network)
            safe_net = re.sub(r"[^A-Za-z0-9_-]", "_", network)
            route_id = f"ROUTE-{serial}-{safe_net}"
            try:
                await neo4j_client.merge_node("Route", route_id, {
                    "id": route_id, "network": network,
                    "display_name": f"Route {network} ({hostname})",
                })
                await neo4j_client.create_relationship("Device", device_id, "HAS_ROUTE", "Route", route_id)
            except Exception:
                pass

        seen_vlans: set[str] = set()
        for vlan in data.get("vlans", []):
            vid = vlan.get("vlan_id", "")
            if not vid or vid in seen_vlans:
                continue
            seen_vlans.add(vid)
            vlan_id_name = f"VLAN-{vid}-{serial}"
            try:
                await neo4j_client.merge_node("VLAN", vlan_id_name, {
                    "id": vlan_id_name, "vlan_id": vid,
                    "name": vlan.get("name", f"VLAN {vid}"),
                    "display_name": f"VLAN {vid} ({hostname})",
                })
                await neo4j_client.create_relationship("Device", device_id, "HAS_VLAN", "VLAN", vlan_id_name)
            except Exception:
                pass

        for neighbor in data.get("topology_neighbors", []):
            nbr_host = neighbor.get("hostname", "")
            nbr_local_if = neighbor.get("local_interface", "")
            nbr_remote_if = neighbor.get("neighbor_interface", "")
            if not nbr_host:
                continue
            try:
                # Find the neighbor device in Neo4j
                found = await neo4j_client.run_query(
                    "MATCH (d:Device) WHERE d.hostname = $host RETURN d.id LIMIT 1",
                    {"host": nbr_host},
                )
                if found:
                    nbr_id = found[0]["d.id"]
                    props = {"source": neighbor.get("protocol", "cdp")}
                    if nbr_local_if:
                        props["local_port"] = nbr_local_if
                    if nbr_remote_if:
                        props["neighbor_port"] = nbr_remote_if
                    await neo4j_client.create_relationship(
                        "Device", device_id, "CONNECTED_TO", "Device", nbr_id, props,
                    )
            except Exception:
                pass

    async def _find_device_by_hostname_ip(self, hostname: str, ip: str) -> dict[str, Any] | None:
        quads = ip.split(".")
        if len(quads) == 4:
            for q in quads:
                if not q.isdigit():
                    return None
        else:
            return None
        try:
            result = await neo4j_client.run_query(
                "MATCH (d:Device) WHERE d.hostname = $hostname AND d.ip = $ip RETURN d.id AS id LIMIT 1",
                {"hostname": hostname, "ip": ip},
            )
            if result and len(result) > 0:
                row = result[0]
                return {"id": row.get("d.id", row.get("id", ""))}
        except Exception:
            pass
        return None

    async def _infer_topology(self) -> None:
        try:
            rows = await neo4j_client.run_query("""
                MATCH (d:Device)-[:HAS_INTERFACE]->(i:Interface)
                WHERE (i.ip IS NOT NULL AND i.ip <> '') OR (i.ip_address IS NOT NULL AND i.ip_address <> '')
                RETURN d.id AS device_id, d.hostname AS hostname,
                       d.type AS dev_type, d.vendor AS dev_vendor,
                       i.id AS iface_id, i.name AS iface_name,
                       coalesce(i.ip, i.ip_address) AS ip,
                       i.mask AS mask
            """)
            if not rows:
                return
            by_subnet: dict[str, list[dict]] = {}
            for row in rows:
                raw_ip = row.get("ip", "")
                mask = row.get("mask", "")
                if not raw_ip or raw_ip == "unassigned":
                    continue
                if "/" in raw_ip:
                    parts = raw_ip.split("/")
                    ip = parts[0]
                    if len(parts) > 1 and not mask:
                        mask = parts[1]
                else:
                    ip = raw_ip
                prefix = 24
                if mask:
                    try:
                        prefix = ipaddress.IPv4Network(f"0.0.0.0/{mask}", strict=False).prefixlen
                    except Exception:
                        pass
                try:
                    net = ipaddress.IPv4Network(f"{ip}/{prefix}", strict=False)
                    subnet_key = str(net)
                except Exception:
                    continue
                if "unassigned" in ip:
                    continue
                by_subnet.setdefault(subnet_key, []).append({
                    "device_id": row.get("device_id", ""),
                    "hostname": row.get("hostname", ""),
                    "dev_type": row.get("dev_type", ""),
                    "dev_vendor": row.get("dev_vendor", ""),
                    "iface_id": row.get("iface_id", ""),
                    "iface_name": row.get("iface_name", ""),
                    "ip": ip,
                })

            # ── Phase 1: CONNECTED_TO (same subnet) ──────────────────
            for subnet, members in by_subnet.items():
                created = 0
                for i in range(len(members)):
                    for j in range(i + 1, len(members)):
                        a, b = members[i], members[j]
                        if a["device_id"] == b["device_id"]:
                            continue
                        try:
                            await neo4j_client.create_relationship(
                                "Device", a["device_id"], "CONNECTED_TO", "Device", b["device_id"]
                            )
                            created += 1
                        except ValueError as e:
                            logger.warning("Topology skip %s→%s: %s", a["hostname"], b["hostname"], e)
                        except Exception as e:
                            logger.warning("Topology error %s→%s: %s", a["hostname"], b["hostname"], e)

            # ── Phase 2: PROTECTS (firewall → all non-firewall devices) ──
            fw_rows = await neo4j_client.run_query("""
                MATCH (d:Device)
                WHERE d.type IN ['firewall', 'ftd', 'cisco-ftd'] OR toLower(d.vendor) CONTAINS 'ftd'
                RETURN d.id AS id
            """)
            fw_device_ids = {r["id"] for r in fw_rows}

            if fw_device_ids:
                dev_rows = await neo4j_client.run_query("""
                    MATCH (d:Device)
                    WHERE NOT (d.type IN ['firewall', 'ftd', 'cisco-ftd'] OR toLower(d.vendor) CONTAINS 'ftd')
                    RETURN d.id AS id
                """)
                dev_ids = [r["id"] for r in dev_rows]

                for fw_id in fw_device_ids:
                    for dev_id in dev_ids:
                        try:
                            await neo4j_client.create_relationship(
                                "Device", fw_id, "PROTECTS", "Device", dev_id,
                                {"source": "topology_inference"},
                            )
                        except ValueError:
                            pass
                        except Exception:
                            pass

            logger.info("Topology inference: %d subnets analysed, relationships created", len(by_subnet))
        except Exception as e:
            logger.warning("Topology inference failed: %s", e)

    async def validate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": self._fingerprint.get("vendor", "unknown"), "valid": False, "error": "not implemented"}

    async def simulate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": self._fingerprint.get("vendor", "unknown"), "simulation": "not implemented"}

    async def apply_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": self._fingerprint.get("vendor", "unknown"), "applied": False, "error": "not implemented"}
