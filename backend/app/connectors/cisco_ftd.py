"""Cisco FTD connector (API first, SSH fallback).

Syncs firewall identity, interfaces, routes, access-list rules and VPN tunnels
from Cisco Secure Firewall / FTD devices into the Neo4j graph.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
from typing import Any

import requests
import urllib3

from app.connectors.base import BaseConnector, SyncResult
from app.connectors import display_name
from app.graph.neo4j_client import neo4j_client
from app.utils.logging import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = get_logger(__name__)


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip()).strip("_") or "unknown"


def _clean_value(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def _mask_to_prefix(mask: str) -> int | None:
    try:
        return ipaddress.IPv4Network(f"0.0.0.0/{mask}").prefixlen
    except Exception:
        return None


def _network_from_ip_mask(address: str, mask: str) -> str | None:
    prefix = _mask_to_prefix(mask)
    if prefix is None:
        return None
    try:
        network = ipaddress.IPv4Network(f"{address}/{prefix}", strict=False)
    except Exception:
        return None
    return str(network)


def _find_values(obj: Any, key: str) -> list[Any]:
    matches: list[Any] = []
    if isinstance(obj, dict):
        for current_key, value in obj.items():
            if current_key == key:
                matches.append(value)
            matches.extend(_find_values(value, key))
    elif isinstance(obj, list):
        for item in obj:
            matches.extend(_find_values(item, key))
    return matches


def _first_text(obj: Any, keys: list[str], default: str = "") -> str:
    for key in keys:
        for value in _find_values(obj, key):
            if isinstance(value, str) and value.strip():
                return value.strip()
    return default


def _first_items(obj: Any) -> list[dict[str, Any]]:
    if isinstance(obj, list):
        return [item for item in obj if isinstance(item, dict)]
    for key in ["items", "objects", "data"]:
        values = _find_values(obj, key)
        for value in values:
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


class CiscoFTDConnector(BaseConnector):
    def __init__(self, config: dict[str, Any]) -> None:
        self.host = config.get("host", "")
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        self.port = int(config.get("port", 22))
        self.verify_ssl = bool(config.get("verify_ssl", False))
        self.transport = str(config.get("transport", "auto")).strip().lower() or "auto"
        self.api_bases = [
            f"https://{self.host}/api/fdm/latest",
            f"https://{self.host}/api/fdm/v6",
        ]

    def _run_ssh(self, command: str) -> str:
        import paramiko

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            timeout=10,
            banner_timeout=20,
            auth_timeout=20,
            look_for_keys=False,
            allow_agent=False,
        )
        try:
            _stdin, stdout, stderr = client.exec_command(command, timeout=30)
            stdout.channel.settimeout(30)
            out = stdout.read().decode(errors="ignore")
            err = stderr.read().decode(errors="ignore")
            return out if out.strip() else err
        finally:
            client.close()

    @staticmethod
    def _is_cli_error(output: str) -> bool:
        text = output.lower()
        return any(marker in text for marker in [
            "% invalid",
            "invalid input",
            "incomplete command",
            "unknown command",
            "syntax error",
            "error:",
        ])

    def _run_first_success(self, commands: list[str]) -> tuple[str, str]:
        last_error: str | None = None
        for command in commands:
            output = self._run_ssh(command)
            if output.strip() and not self._is_cli_error(output):
                return command, output
            last_error = output.strip() or f"No output for command: {command}"
        raise RuntimeError(last_error or "No CLI command produced usable output")

    def _api_login(self, api_base: str) -> str:
        response = requests.post(
            f"{api_base}/fdm/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "password",
                "username": self.username,
                "password": self.password,
            },
            verify=self.verify_ssl,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        token = str(payload.get("access_token", "")).strip()
        if not token:
            raise RuntimeError("Cisco FTD API login succeeded without access_token")
        return token

    def _api_get(self, api_base: str, token: str, path: str) -> Any:
        response = requests.get(
            f"{api_base}{path}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            verify=self.verify_ssl,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def _api_get_first_success(self, api_base: str, token: str, paths: list[str]) -> tuple[str, Any]:
        last_exc: Exception | None = None
        for path in paths:
            try:
                return path, self._api_get(api_base, token, path)
            except requests.RequestException as exc:
                last_exc = exc
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("No Cisco FTD API endpoint candidates were provided")

    def _consume_endpoint(self, tokens: list[str]) -> tuple[str, list[str]]:
        if not tokens:
            return "any", []

        head = tokens[0].lower()
        if head in {"any", "any4", "any6"}:
            return head, tokens[1:]
        if head == "host" and len(tokens) >= 2:
            return f"host {tokens[1]}", tokens[2:]
        if head in {"object", "object-group", "interface"} and len(tokens) >= 2:
            return f"{head} {tokens[1]}", tokens[2:]
        if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", tokens[0]):
            if len(tokens) >= 2 and re.fullmatch(r"\d+\.\d+\.\d+\.\d+", tokens[1]):
                network = _network_from_ip_mask(tokens[0], tokens[1])
                if network:
                    return network, tokens[2:]
            return tokens[0], tokens[1:]
        return tokens[0], tokens[1:]

    def _parse_version(self, output: str) -> dict[str, str]:
        hostname = self.host
        serial = _safe_id(self.host)
        model = ""
        os_version = ""

        patterns = {
            "hostname": [
                r"^Hostname:\s*(\S+)",
                r"^Cisco Firepower Threat Defense for\s+(\S+)",
                r"^(\S+)\s+up\s+\d+",
            ],
            "serial": [
                r"^Serial Number:\s*(\S+)",
                r"^Processor board ID\s+(\S+)",
            ],
            "model": [
                r"^Model\s*:\s*(.+)",
                r"^Hardware:\s*([^,]+)",
            ],
            "version": [
                r"^Version\s+([A-Za-z0-9()._-]+)",
                r"Cisco Firepower Threat Defense.*Version\s+([A-Za-z0-9()._-]+)",
            ],
        }

        for line in output.splitlines():
            stripped = line.strip()
            for pattern in patterns["hostname"]:
                match = re.search(pattern, stripped, re.IGNORECASE)
                if match:
                    hostname = match.group(1)
                    break
            for pattern in patterns["serial"]:
                match = re.search(pattern, stripped, re.IGNORECASE)
                if match:
                    serial = _safe_id(match.group(1))
                    break
            if not model:
                for pattern in patterns["model"]:
                    match = re.search(pattern, stripped, re.IGNORECASE)
                    if match:
                        model = _clean_value(match.group(1))
                        break
            if not os_version:
                for pattern in patterns["version"]:
                    match = re.search(pattern, stripped, re.IGNORECASE)
                    if match:
                        os_version = match.group(1)
                        break

        return {
            "hostname": hostname,
            "serial": serial,
            "model": model,
            "os_version": os_version,
        }

    def _parse_api_device_facts(self, payload: Any) -> dict[str, str]:
        hostname = _first_text(payload, ["hostname", "name"], self.host)
        serial = _safe_id(_first_text(payload, ["serial", "serialNumber"], self.host))
        model = _first_text(payload, ["model", "modelName"])
        os_version = _first_text(payload, ["version", "softwareVersion"])
        return {
            "hostname": hostname,
            "serial": serial,
            "model": model,
            "os_version": os_version,
        }

    def _parse_interfaces(self, output: str) -> list[dict[str, str]]:
        interfaces: list[dict[str, str]] = []
        seen: set[str] = set()

        for line in output.splitlines():
            stripped = line.strip()
            brief = re.match(
                r"^(\S+)\s+(\S+)\s+\S+\s+\S+\s+(administratively down|up|down)\s+(up|down)$",
                stripped,
                re.IGNORECASE,
            )
            if brief:
                name = brief.group(1)
                if name in seen:
                    continue
                seen.add(name)
                ip_addr = brief.group(2)
                admin_status = brief.group(3).lower()
                line_status = brief.group(4).lower()
                status = "up" if admin_status == "up" and line_status == "up" else admin_status
                interfaces.append({
                    "name": name,
                    "status": status,
                    "ip_address": "" if ip_addr.lower() == "unassigned" else ip_addr,
                })
                continue

            detail = re.match(
                r'^(\S+)(?:\s+"[^"]+")?,\s+is\s+(administratively down|up|down),\s+line protocol is\s+(up|down)',
                stripped,
                re.IGNORECASE,
            )
            if detail:
                name = detail.group(1)
                if name in seen:
                    continue
                seen.add(name)
                admin_status = detail.group(2).lower()
                line_status = detail.group(3).lower()
                status = "up" if admin_status == "up" and line_status == "up" else admin_status
                interfaces.append({"name": name, "status": status, "ip_address": ""})

        return interfaces

    def _parse_api_interfaces(self, payload: Any) -> list[dict[str, str]]:
        interfaces: list[dict[str, str]] = []
        for item in _first_items(payload):
            name = str(item.get("name") or item.get("ifname") or "").strip()
            if not name:
                continue
            enabled = item.get("enabled")
            status = "up" if enabled is True else "down" if enabled is False else "unknown"
            ip_address = ""
            if isinstance(item.get("ipAddress"), dict):
                ip_address = str(item["ipAddress"].get("value") or "").strip()
            elif isinstance(item.get("ipAddress"), str):
                ip_address = item.get("ipAddress", "").strip()
            interfaces.append({"name": name, "status": status, "ip_address": ip_address})
        return interfaces

    def _parse_routes(self, output: str) -> list[dict[str, str]]:
        routes: list[dict[str, str]] = []
        seen: set[str] = set()

        for line in output.splitlines():
            stripped = line.strip()
            cidr_match = re.search(r"(\d+\.\d+\.\d+\.\d+/\d+)", stripped)
            network = cidr_match.group(1) if cidr_match else None
            if network is None:
                mask_match = re.match(
                    r"^[A-Z*]+\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)",
                    stripped,
                    re.IGNORECASE,
                )
                if mask_match:
                    network = _network_from_ip_mask(mask_match.group(1), mask_match.group(2))
            if network is None or network in seen:
                continue
            seen.add(network)
            routes.append({"network": network})

        return routes

    def _parse_api_routes(self, payload: Any) -> list[dict[str, str]]:
        routes: list[dict[str, str]] = []
        for item in _first_items(payload):
            network = str(item.get("network") or "").strip()
            if not network:
                ip_address = str(item.get("ipAddress") or item.get("gateway") or "").strip()
                mask = str(item.get("netMask") or item.get("mask") or "").strip()
                if ip_address and mask:
                    network = _network_from_ip_mask(ip_address, mask) or ""
            if network:
                routes.append({"network": network})
        return routes

    def _parse_rules(self, output: str) -> list[dict[str, str]]:
        rules: list[dict[str, str]] = []

        for line in output.splitlines():
            stripped = line.strip()
            match = re.match(
                r"^access-list\s+(\S+)(?:\s+line\s+(\d+))?\s+(?:extended\s+|standard\s+)?(permit|deny)\s+(.+)$",
                stripped,
                re.IGNORECASE,
            )
            if not match:
                continue

            acl_name = match.group(1)
            line_no = match.group(2) or str(len(rules) + 1)
            action = match.group(3).lower()
            remainder_tokens = match.group(4).split()
            if not remainder_tokens:
                continue

            protocol = remainder_tokens[0].lower()
            source, remainder_tokens = self._consume_endpoint(remainder_tokens[1:])
            destination, remainder_tokens = self._consume_endpoint(remainder_tokens)

            port = "any"
            if remainder_tokens:
                head = remainder_tokens[0].lower()
                if head == "eq" and len(remainder_tokens) >= 2:
                    port = remainder_tokens[1]
                elif head == "range" and len(remainder_tokens) >= 3:
                    port = f"{remainder_tokens[1]}-{remainder_tokens[2]}"
                elif head in {"lt", "gt", "neq"} and len(remainder_tokens) >= 2:
                    port = f"{head} {remainder_tokens[1]}"

            rules.append({
                "acl_name": acl_name,
                "line_no": line_no,
                "name": f"{acl_name} line {line_no}",
                "protocol": protocol,
                "source": source,
                "destination": destination,
                "port": port,
                "action": action,
            })

        return rules

    def _parse_api_rules(self, payload: Any) -> list[dict[str, str]]:
        rules: list[dict[str, str]] = []
        for item in _first_items(payload):
            name = str(item.get("name") or item.get("ruleName") or "").strip()
            if not name:
                continue
            action = str(item.get("action") or "allow").strip().lower()
            source = _first_text(item, ["sourceNetworks", "sourceZones"], "any") or "any"
            destination = _first_text(item, ["destinationNetworks", "destinationZones"], "any") or "any"
            port = _first_text(item, ["destinationPorts", "sourcePorts"], "any") or "any"
            protocol = _first_text(item, ["ruleType", "protocol"], "ip") or "ip"
            rules.append({
                "acl_name": "api",
                "line_no": str(len(rules) + 1),
                "name": name,
                "protocol": protocol,
                "source": source,
                "destination": destination,
                "port": port,
                "action": action,
            })
        return rules

    def _parse_vpn_tunnels(self, output: str) -> list[dict[str, str]]:
        tunnels: list[dict[str, str]] = []
        current_name: str | None = None
        current_peer: str | None = None
        seen: set[str] = set()

        for line in output.splitlines():
            stripped = line.strip()
            name_match = re.search(r"(?:Connection|Tunnel)\s*:?\s*(\S+)", stripped, re.IGNORECASE)
            if name_match:
                current_name = name_match.group(1)
            peer_match = re.search(r"(?:Peer(?: IP Address)?|Remote Gateway|Remote Address)\s*:?\s*(\d+\.\d+\.\d+\.\d+)", stripped, re.IGNORECASE)
            if peer_match:
                current_peer = peer_match.group(1)

            generic_peer = re.search(r"peer address:\s*(\d+\.\d+\.\d+\.\d+)", stripped, re.IGNORECASE)
            if generic_peer:
                current_peer = generic_peer.group(1)

            if current_name or current_peer:
                tunnel_key = current_name or current_peer or ""
                if tunnel_key and tunnel_key not in seen:
                    tunnels.append({
                        "name": current_name or current_peer or tunnel_key,
                        "peer": current_peer or "",
                    })
                    seen.add(tunnel_key)
                    current_name = None
                    current_peer = None

        return tunnels

    def _parse_api_vpn_tunnels(self, payload: Any) -> list[dict[str, str]]:
        tunnels: list[dict[str, str]] = []
        for item in _first_items(payload):
            name = str(item.get("name") or item.get("connectionName") or item.get("peerName") or "").strip()
            peer = str(item.get("peer") or item.get("peerAddress") or item.get("remoteGateway") or "").strip()
            if name or peer:
                tunnels.append({"name": name or peer, "peer": peer})
        return tunnels

    async def _merge_inventory(
        self,
        result: SyncResult,
        hostname: str,
        device_id: str,
        device_dn: str,
        model: str,
        os_version: str,
        interfaces: list[dict[str, str]],
        routes: list[dict[str, str]],
        rules: list[dict[str, str]],
        tunnels: list[dict[str, str]],
    ) -> None:
        await neo4j_client.merge_node("Device", device_id, {
            "id": device_id,
            "type": "firewall",
            "vendor": "cisco",
            "hostname": hostname,
            "criticality": "critical",
            "model": model,
            "os_version": os_version,
            "display_name": device_dn,
        })
        result.record_success("devices")

        for interface in interfaces:
            iface_id = f"IF-FTD-{_safe_id(hostname)}-{_safe_id(interface['name'])}"
            await neo4j_client.merge_node("Interface", iface_id, {
                "id": iface_id,
                "name": interface["name"],
                "status": interface["status"],
                "ip_address": interface.get("ip_address", ""),
                "display_name": display_name.interface(interface["name"], device_dn),
            })
            await neo4j_client.create_relationship("Device", device_id, "HAS_INTERFACE", "Interface", iface_id)
            result.record_success("interfaces")

        for route in routes:
            route_id = f"ROUTE-FTD-{_safe_id(hostname)}-{_safe_id(route['network'])}"
            await neo4j_client.merge_node("Route", route_id, {
                "id": route_id,
                "network": route["network"],
                "display_name": f"Route {route['network']}  ({hostname})",
            })
            await neo4j_client.create_relationship("Device", device_id, "HAS_ROUTE", "Route", route_id)
            result.record_success("routes")

        for rule in rules:
            rule_id = f"FTD-RULE-{_safe_id(hostname)}-{_safe_id(rule['acl_name'])}-{_safe_id(rule['line_no'])}"
            await neo4j_client.merge_node("Rule", rule_id, {
                "id": rule_id,
                "name": rule["name"],
                "source": rule["source"],
                "destination": rule["destination"],
                "port": rule["port"],
                "protocol": rule["protocol"],
                "action": rule["action"],
                "display_name": display_name.rule(rule["name"], device_dn),
            })
            await neo4j_client.create_relationship("Device", device_id, "HAS_RULE", "Rule", rule_id)

            destination = rule["destination"].lower()
            if destination not in {"any", "any4", "any6", ""}:
                app_name = rule["destination"].replace("host ", "").replace("object ", "").replace("object-group ", "")
                app_id = f"APP-{_safe_id(app_name)}"
                await neo4j_client.merge_node("Application", app_id, {
                    "id": app_id,
                    "name": app_name,
                    "label": app_name,
                    "criticality": "medium",
                    "display_name": display_name.application(app_name),
                })
                await neo4j_client.create_relationship("Rule", rule_id, "PROTECTS", "Application", app_id)

            result.record_success("rules")

        for tunnel in tunnels:
            tunnel_key = tunnel["peer"] or tunnel["name"]
            tunnel_id = f"VPN-TUNNEL-FTD-{_safe_id(hostname)}-{_safe_id(tunnel_key)}"
            label = tunnel["peer"] or tunnel["name"]
            await neo4j_client.merge_node("VPNTunnel", tunnel_id, {
                "id": tunnel_id,
                "name": tunnel["name"],
                "peer": tunnel["peer"],
                "display_name": f"VPN Tunnel to {label}  ({hostname})",
            })
            await neo4j_client.create_relationship("Device", device_id, "HAS_VPN_TUNNEL", "VPNTunnel", tunnel_id)
            result.record_success("vpn_tunnels")

    async def _sync_via_api(self, result: SyncResult) -> bool:
        last_exc: Exception | None = None

        for api_base in self.api_bases:
            try:
                token = await asyncio.to_thread(self._api_login, api_base)
                _device_path, device_payload = await asyncio.to_thread(
                    self._api_get_first_success,
                    api_base,
                    token,
                    [
                        "/devices/default/deviceversion",
                        "/devices/default/devices/default",
                        "/devices/default/device",
                    ],
                )
                facts = self._parse_api_device_facts(device_payload)
                hostname = facts["hostname"]
                device_id = f"FTD-{facts['serial']}"
                device_dn = display_name.device(display_name.VENDOR_CISCO, display_name.FUNCTION_FIREWALL, hostname)

                interfaces: list[dict[str, str]] = []
                routes: list[dict[str, str]] = []
                rules: list[dict[str, str]] = []
                tunnels: list[dict[str, str]] = []

                try:
                    _iface_path, iface_payload = await asyncio.to_thread(
                        self._api_get_first_success,
                        api_base,
                        token,
                        [
                            "/devices/default/interfaces/physicalinterfaces?limit=200",
                            "/devices/default/interfaces/ethernetinterfaces?limit=200",
                            "/devices/default/interfaces?limit=200",
                        ],
                    )
                    interfaces = self._parse_api_interfaces(iface_payload)
                except Exception as exc:
                    result.record_failure("interfaces", f"api: {exc}")

                try:
                    _route_path, route_payload = await asyncio.to_thread(
                        self._api_get_first_success,
                        api_base,
                        token,
                        [
                            "/devices/default/routing/ipv4staticroutes?limit=200",
                            "/devices/default/routing/ipv4staticroutes",
                        ],
                    )
                    routes = self._parse_api_routes(route_payload)
                except Exception as exc:
                    result.record_failure("routes", f"api: {exc}")

                try:
                    _rule_path, rule_payload = await asyncio.to_thread(
                        self._api_get_first_success,
                        api_base,
                        token,
                        [
                            "/policy/accesspolicies/default/accessrules?limit=200",
                            "/devices/default/accesspolicies/default/accessrules?limit=200",
                        ],
                    )
                    rules = self._parse_api_rules(rule_payload)
                except Exception as exc:
                    result.record_failure("rules", f"api: {exc}")

                try:
                    _vpn_path, vpn_payload = await asyncio.to_thread(
                        self._api_get_first_success,
                        api_base,
                        token,
                        [
                            "/devices/default/vpn/s2svpntunnels?limit=200",
                            "/devices/default/vpn/s2svpntunnels",
                        ],
                    )
                    tunnels = self._parse_api_vpn_tunnels(vpn_payload)
                except Exception as exc:
                    result.record_failure("vpn_tunnels", f"api: {exc}")

                await self._merge_inventory(
                    result,
                    hostname,
                    device_id,
                    device_dn,
                    facts["model"],
                    facts["os_version"],
                    interfaces,
                    routes,
                    rules,
                    tunnels,
                )
                return True
            except Exception as exc:
                last_exc = exc
                logger.warning("Cisco FTD API sync failed for %s using %s: %s", self.host, api_base, exc)

        if last_exc is not None:
            result.record_failure("devices", f"api: {last_exc}")
        return False

    async def _sync_via_ssh(self, result: SyncResult) -> None:
        _version_command, version_out = await asyncio.to_thread(self._run_first_success, ["show version"])
        facts = self._parse_version(version_out)
        hostname = facts["hostname"]
        device_id = f"FTD-{facts['serial']}"
        device_dn = display_name.device(display_name.VENDOR_CISCO, display_name.FUNCTION_FIREWALL, hostname)

        interfaces: list[dict[str, str]] = []
        routes: list[dict[str, str]] = []
        rules: list[dict[str, str]] = []
        tunnels: list[dict[str, str]] = []

        try:
            _iface_command, iface_out = await asyncio.to_thread(
                self._run_first_success,
                ["show interface ip brief", "show interfaces ip brief", "show interfaces"],
            )
            interfaces = self._parse_interfaces(iface_out)
        except Exception as exc:
            result.record_failure("interfaces", str(exc))

        try:
            _route_command, route_out = await asyncio.to_thread(self._run_first_success, ["show route", "show ip route"])
            routes = self._parse_routes(route_out)
        except Exception as exc:
            result.record_failure("routes", str(exc))

        try:
            _rule_command, rule_out = await asyncio.to_thread(self._run_first_success, ["show access-list"])
            rules = self._parse_rules(rule_out)
        except Exception as exc:
            result.record_failure("rules", str(exc))

        try:
            _vpn_command, vpn_out = await asyncio.to_thread(
                self._run_first_success,
                ["show vpn-sessiondb detail l2l", "show vpn-sessiondb summary", "show crypto ipsec sa"],
            )
            tunnels = self._parse_vpn_tunnels(vpn_out)
        except Exception as exc:
            result.record_failure("vpn_tunnels", str(exc))

        await self._merge_inventory(
            result,
            hostname,
            device_id,
            device_dn,
            facts["model"],
            facts["os_version"],
            interfaces,
            routes,
            rules,
            tunnels,
        )

    async def sync(self) -> dict[str, Any]:
        result = SyncResult()
        if self.transport in {"auto", "api"}:
            api_ok = await self._sync_via_api(result)
            if api_ok:
                result.finalise()
                return {"vendor": "cisco-ftd", **result.to_dict()}
            if self.transport == "api":
                result.finalise()
                return {"vendor": "cisco-ftd", **result.to_dict()}

        try:
            await self._sync_via_ssh(result)
        except Exception as exc:
            result.record_failure("devices", str(exc))

        result.finalise()
        return {"vendor": "cisco-ftd", **result.to_dict()}

    async def validate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "cisco-ftd", "valid": False, "error": "not implemented"}

    async def simulate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "cisco-ftd", "simulation": "not implemented"}

    async def apply_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"vendor": "cisco-ftd", "applied": False, "error": "not implemented"}