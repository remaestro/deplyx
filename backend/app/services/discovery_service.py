import asyncio
import ipaddress
import socket
import ssl
import struct
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

import paramiko
import requests
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.connector import Connector
from app.models.discovery import DiscoveryResult, DiscoverySession
from app.services import connector_service


DEFAULT_HTTP_PATHS = ("/", "/api", "/api/v1", "/health")
DEFAULT_DISCOVERY_PORTS = [22, 80, 161, 389, 443, 636, 3000, 5432, 6379, 8080, 8443, 9090, 9200]
HTTP_PORTS = {80, 443, 3000, 8080, 8443, 9090, 9200}
SSH_PORT = 22
SNMP_PORT = 161
LDAP_PORT = 389
LDAPS_PORT = 636
MGMT_API_PORTS = {443, 8443}
POSTGRES_PORT = 5432
REDIS_PORT = 6379
MAX_CIDR_HOSTS = 256
PROBE_CONCURRENCY = 32
SSH_CONNECTOR_TYPES = {
    "aruba-ap",
    "aruba-switch",
    "cisco",
    "cisco-ftd",
    "cisco-nxos",
    "cisco-router",
    "cisco-wlc",
    "elasticsearch",
    "grafana",
    "juniper",
    "nginx",
    "openldap",
    "postgres",
    "prometheus",
    "redis",
    "snort",
    "strongswan",
    "vyos",
}


@dataclass(slots=True)
class PreparedTarget:
    host: str
    source_kind: str
    name_hint: str | None = None
    declared_connector_type: str | None = None
    metadata: dict[str, Any] | None = None


async def create_discovery_session(db: AsyncSession, data: dict[str, Any]) -> DiscoverySession:
    prepared_targets, sanitized_input = _prepare_targets(data)
    ports = _normalize_ports(data.get("ports") or [])
    timeout_seconds = _normalize_timeout(data.get("timeout_seconds", 3))

    session = DiscoverySession(
        name=data.get("name"),
        status="running",
        input_payload=sanitized_input,
        ports=ports,
        timeout_seconds=timeout_seconds,
        target_count=len(prepared_targets),
        started_at=datetime.now(UTC),
    )
    db.add(session)
    await db.flush()

    try:
        probe_payloads = await _probe_targets(prepared_targets, ports, timeout_seconds)
        for payload in probe_payloads:
            db.add(DiscoveryResult(session_id=session.id, **payload))

        session.summary = _build_summary(probe_payloads)
        session.status = "completed"
        session.completed_at = datetime.now(UTC)
        session.last_error = None
    except Exception as exc:
        session.status = "error"
        session.completed_at = datetime.now(UTC)
        session.last_error = str(exc)
        await db.flush()
        raise

    await db.flush()
    await db.refresh(session)
    return await get_discovery_session(db, session.id, include_results=True)


async def list_discovery_sessions(db: AsyncSession) -> list[DiscoverySession]:
    result = await db.execute(select(DiscoverySession).order_by(DiscoverySession.id.desc()))
    return list(result.scalars().all())


async def get_discovery_session(
    db: AsyncSession,
    session_id: int,
    *,
    include_results: bool = False,
) -> DiscoverySession | None:
    stmt = select(DiscoverySession).where(DiscoverySession.id == session_id)
    if include_results:
        stmt = stmt.options(selectinload(DiscoverySession.results))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_discovery_results(db: AsyncSession, session_id: int) -> list[DiscoveryResult]:
    result = await db.execute(
        select(DiscoveryResult)
        .where(DiscoveryResult.session_id == session_id)
        .order_by(DiscoveryResult.id)
    )
    return list(result.scalars().all())


async def bootstrap_discovery_session(db: AsyncSession, session_id: int, data: dict[str, Any]) -> dict[str, Any]:
    session = await get_discovery_session(db, session_id, include_results=True)
    if session is None:
        raise ValueError("Discovery session not found")

    existing_connectors = await connector_service.list_connectors(db)
    existing_by_host = {
        str((connector.config or {}).get("host", "")).strip(): connector
        for connector in existing_connectors
        if str((connector.config or {}).get("host", "")).strip()
    }

    created = 0
    synced = 0
    skipped = 0
    errors = 0
    items: list[dict[str, Any]] = []

    connector_defaults = data.get("connector_defaults") or {}
    default_config = data.get("default_config") or {}
    run_sync = bool(data.get("run_sync", True))
    allow_ambiguous = bool(data.get("allow_ambiguous", False))
    on_existing = str(data.get("on_existing", "skip") or "skip")
    selection_by_result_id = _normalize_bootstrap_selections(session.results, data.get("items") or [])
    selected_results = [
        result
        for result in session.results
        if not selection_by_result_id or result.id in selection_by_result_id
    ]

    for result in selected_results:
        selection = selection_by_result_id.get(result.id, {})
        item = await _bootstrap_result(
            db,
            result,
            existing_by_host,
            connector_defaults=connector_defaults,
            default_config=default_config,
            sync_mode=str(data.get("sync_mode", "on-demand") or "on-demand"),
            sync_interval_minutes=int(data.get("sync_interval_minutes", 60) or 60),
            run_sync=run_sync,
            allow_ambiguous=allow_ambiguous,
            on_existing=on_existing,
            connector_type_override=selection.get("connector_type"),
            run_sync_override=selection.get("run_sync"),
        )
        items.append(item)
        status = item["bootstrap_status"]
        if status == "created":
            created += 1
        elif status == "synced":
            synced += 1
        elif status.startswith("skipped"):
            skipped += 1
        elif status == "error":
            errors += 1

    session.summary = {
        **(session.summary or {}),
        "bootstrap": {
            "processed": len(items),
            "created": created,
            "synced": synced,
            "skipped": skipped,
            "errors": errors,
        },
    }
    await db.flush()
    return {
        "session_id": session_id,
        "processed": len(items),
        "created": created,
        "synced": synced,
        "skipped": skipped,
        "errors": errors,
        "items": items,
    }


def _prepare_targets(data: dict[str, Any]) -> tuple[list[PreparedTarget], dict[str, Any]]:
    max_targets = int(data.get("max_targets", 128) or 128)
    prepared: list[PreparedTarget] = []
    seen: set[str] = set()
    sanitized_input = {
        "targets": [],
        "cidrs": list(data.get("cidrs") or []),
        "inventory": [],
    }

    for raw_host in data.get("targets") or []:
        host = str(raw_host).strip()
        if not host or host in seen:
            continue
        prepared.append(PreparedTarget(host=host, source_kind="target"))
        sanitized_input["targets"].append(host)
        seen.add(host)

    for item in data.get("inventory") or []:
        host = str(item.get("host", "")).strip()
        if not host or host in seen:
            continue
        prepared.append(
            PreparedTarget(
                host=host,
                source_kind="inventory",
                name_hint=item.get("name"),
                declared_connector_type=item.get("connector_type"),
                metadata=item.get("metadata") or {},
            )
        )
        sanitized_input["inventory"].append(
            {
                "host": host,
                "name": item.get("name"),
                "connector_type": item.get("connector_type"),
                "metadata": item.get("metadata") or {},
            }
        )
        seen.add(host)

    for cidr in data.get("cidrs") or []:
        network = ipaddress.ip_network(str(cidr).strip(), strict=False)
        hosts = [str(host) for host in network.hosts()]
        if len(hosts) > MAX_CIDR_HOSTS:
            raise ValueError(f"CIDR {cidr} expands to {len(hosts)} hosts; limit is {MAX_CIDR_HOSTS}")
        for host in hosts:
            if host in seen:
                continue
            prepared.append(PreparedTarget(host=host, source_kind="cidr"))
            seen.add(host)

    if not prepared:
        raise ValueError("No discovery targets were derived from the request")
    if len(prepared) > max_targets:
        raise ValueError(f"Discovery request expands to {len(prepared)} targets; limit is {max_targets}")
    return prepared, sanitized_input


def _normalize_ports(raw_ports: list[Any]) -> list[int]:
    ports = []
    for raw_port in raw_ports:
        port = int(raw_port)
        if port < 1 or port > 65535:
            raise ValueError(f"Invalid port: {port}")
        if port not in ports:
            ports.append(port)
    if not ports:
        return list(DEFAULT_DISCOVERY_PORTS)
    return ports


def _normalize_timeout(raw_timeout: Any) -> int:
    timeout_seconds = int(raw_timeout)
    if timeout_seconds < 1 or timeout_seconds > 15:
        raise ValueError("timeout_seconds must be between 1 and 15")
    return timeout_seconds


async def _probe_targets(targets: list[PreparedTarget], ports: list[int], timeout_seconds: int) -> list[dict[str, Any]]:
    semaphore = asyncio.Semaphore(PROBE_CONCURRENCY)

    async def _run(target: PreparedTarget) -> dict[str, Any]:
        async with semaphore:
            return await _probe_target(target, ports, timeout_seconds)

    return list(await asyncio.gather(*[_run(target) for target in targets]))


async def _probe_target(target: PreparedTarget, ports: list[int], timeout_seconds: int) -> dict[str, Any]:
    port_results = await asyncio.gather(
        *[_tcp_probe(target.host, port, timeout_seconds) for port in ports]
    )
    open_ports = [item["port"] for item in port_results if item["open"]]
    open_port_set = set(open_ports)

    ssh_banner = None
    if SSH_PORT in open_port_set:
        ssh_banner = await _read_ssh_banner(target.host, SSH_PORT, timeout_seconds)

    http_probes = []
    for port in open_ports:
        if port in HTTP_PORTS:
            http_probes.append(await _probe_http(target.host, port, timeout_seconds))

    redis_probe = None
    if REDIS_PORT in open_port_set:
        redis_probe = await _probe_redis(target.host, REDIS_PORT, timeout_seconds)

    postgres_probe = None
    if POSTGRES_PORT in open_port_set:
        postgres_probe = await _probe_postgres(target.host, POSTGRES_PORT, timeout_seconds)

    ldap_probe = None
    if LDAP_PORT in open_port_set:
        ldap_probe = await _probe_ldap(target.host, LDAP_PORT, timeout_seconds, use_ssl=False)
    if ldap_probe is None and LDAPS_PORT in open_port_set:
        ldap_probe = await _probe_ldap(target.host, LDAPS_PORT, timeout_seconds, use_ssl=True)

    snmp_probe = None
    if SNMP_PORT in ports:
        snmp_probe = await asyncio.to_thread(_probe_snmp, target.host, SNMP_PORT, timeout_seconds)

    management_api_probes: dict[str, dict[str, Any]] = {}
    if open_port_set & MGMT_API_PORTS:
        management_api_probes = await _probe_vendor_management_apis(target.host, open_port_set, timeout_seconds)

    evidence = _build_evidence(open_ports, redis_probe, postgres_probe, ldap_probe, snmp_probe, management_api_probes)

    facts = {
        "open_ports": open_ports,
        "ssh_banner": ssh_banner,
        "http": [probe for probe in http_probes if probe],
        "redis": redis_probe,
        "postgres": postgres_probe,
        "ldap": ldap_probe,
        "snmp_probe": snmp_probe,
        "management_apis": management_api_probes,
        "evidence": evidence,
    }
    suggested_connector_types, selected_connector_type, reasons = _classify_target(target, facts)
    status = "reachable" if evidence["reachable"] else "unreachable"

    return {
        "host": target.host,
        "name_hint": target.name_hint,
        "source_kind": target.source_kind,
        "status": status,
        "selected_connector_type": selected_connector_type,
        "suggested_connector_types": suggested_connector_types,
        "probe_detail": {
            "ports": port_results,
            "http": [probe for probe in http_probes if probe],
            "redis": redis_probe,
            "postgres": postgres_probe,
            "ldap": ldap_probe,
            "snmp": snmp_probe,
            "management_apis": management_api_probes,
        },
        "facts": facts,
        "classification_reasons": reasons,
        "error": None if evidence["reachable"] else "No known discovery probe responded",
    }


async def _tcp_probe(host: str, port: int, timeout_seconds: int) -> dict[str, Any]:
    try:
        connection = asyncio.open_connection(host, port)
        reader, writer = await asyncio.wait_for(connection, timeout=timeout_seconds)
        writer.close()
        await writer.wait_closed()
        return {"port": port, "open": True, "error": None}
    except Exception as exc:
        return {"port": port, "open": False, "error": str(exc)}


async def _read_ssh_banner(host: str, port: int, timeout_seconds: int) -> str | None:
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout_seconds)
        banner = await asyncio.wait_for(reader.readline(), timeout=timeout_seconds)
        writer.close()
        await writer.wait_closed()
        text = banner.decode(errors="ignore").strip()
        return text or None
    except Exception:
        return None


async def _probe_http(host: str, port: int, timeout_seconds: int) -> dict[str, Any] | None:
    scheme = "https" if port in {443, 8443} else "http"
    for path in DEFAULT_HTTP_PATHS:
        url = f"{scheme}://{host}:{port}{path}"
        probe = await asyncio.to_thread(_http_request, url, timeout_seconds)
        if probe:
            return probe
    return None


def _http_request(url: str, timeout_seconds: int) -> dict[str, Any] | None:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    req = urllib_request.Request(url, headers={"User-Agent": "deplyx-discovery/0.1"}, method="GET")
    try:
        with urllib_request.urlopen(req, timeout=timeout_seconds, context=context) as response:
            body = response.read(512).decode(errors="ignore")
            return {
                "url": url,
                "status": response.status,
                "server": response.headers.get("Server"),
                "body_snippet": body[:200],
            }
    except urllib_error.HTTPError as exc:
        body = exc.read(512).decode(errors="ignore")
        return {
            "url": url,
            "status": exc.code,
            "server": exc.headers.get("Server"),
            "body_snippet": body[:200],
        }
    except Exception:
        return None


async def _probe_redis(host: str, port: int, timeout_seconds: int) -> dict[str, Any] | None:
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout_seconds)
        writer.write(b"*1\r\n$4\r\nPING\r\n")
        await writer.drain()
        response = await asyncio.wait_for(reader.readline(), timeout=timeout_seconds)
        writer.close()
        await writer.wait_closed()
        text = response.decode(errors="ignore").strip()
        if text.startswith("+PONG"):
            return {"status": "detected", "message": text}
        if text.startswith("-NOAUTH"):
            return {"status": "detected", "message": text}
        if text:
            return {"status": "unknown", "message": text}
        return None
    except Exception:
        return None


async def _probe_postgres(host: str, port: int, timeout_seconds: int) -> dict[str, Any] | None:
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout_seconds)
        writer.write(struct.pack("!II", 8, 80877103))
        await writer.drain()
        response = await asyncio.wait_for(reader.readexactly(1), timeout=timeout_seconds)
        writer.close()
        await writer.wait_closed()
        if response in {b"S", b"N"}:
            return {"status": "detected", "ssl_supported": response == b"S"}
        return {"status": "unknown", "message": response.decode(errors="ignore")}
    except Exception:
        return None


async def _probe_ldap(host: str, port: int, timeout_seconds: int, *, use_ssl: bool) -> dict[str, Any] | None:
    ssl_context = None
    if use_ssl:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=ssl_context),
            timeout=timeout_seconds,
        )
        writer.write(_ldap_bind_request())
        await writer.drain()
        response = await asyncio.wait_for(reader.read(1024), timeout=timeout_seconds)
        writer.close()
        await writer.wait_closed()

        parsed = _parse_ldap_bind_response(response)
        if parsed is None:
            return None
        return {
            "status": "detected",
            "port": port,
            "tls": use_ssl,
            **parsed,
        }
    except Exception:
        return None


def _probe_snmp(host: str, port: int, timeout_seconds: int) -> dict[str, Any] | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout_seconds)
    try:
        sock.sendto(_snmp_sysdescr_request(), (host, port))
        response, _ = sock.recvfrom(2048)
        return _parse_snmp_response(response)
    except Exception:
        return None
    finally:
        sock.close()


async def _probe_vendor_management_apis(
    host: str,
    open_ports: set[int],
    timeout_seconds: int,
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for port in sorted(open_ports & MGMT_API_PORTS):
        fortinet = await asyncio.to_thread(_fortinet_management_probe, host, port, timeout_seconds)
        if fortinet and "fortinet" not in results:
            results["fortinet"] = fortinet

        paloalto = await asyncio.to_thread(_paloalto_management_probe, host, port, timeout_seconds)
        if paloalto and "paloalto" not in results:
            results["paloalto"] = paloalto

        checkpoint = await asyncio.to_thread(_checkpoint_management_probe, host, port, timeout_seconds)
        if checkpoint and "checkpoint" not in results:
            results["checkpoint"] = checkpoint
    return results


def _fortinet_management_probe(host: str, port: int, timeout_seconds: int) -> dict[str, Any] | None:
    try:
        resp = requests.get(
            f"https://{host}:{port}/api/v2/monitor/system/status",
            verify=False,
            timeout=timeout_seconds,
        )
        text = resp.text[:300].lower()
        server = resp.headers.get("Server", "")
        if "forti" in text or "forti" in server.lower() or (resp.status_code in {401, 403} and "application/json" in resp.headers.get("Content-Type", "")):
            return {
                "status": "detected",
                "port": port,
                "status_code": resp.status_code,
                "server": server,
            }
    except requests.RequestException:
        return None
    return None


def _paloalto_management_probe(host: str, port: int, timeout_seconds: int) -> dict[str, Any] | None:
    try:
        resp = requests.get(
            f"https://{host}:{port}/api/?type=op&cmd=<show><system><info></info></system></show>",
            verify=False,
            timeout=timeout_seconds,
        )
        text = resp.text[:400].lower()
        if "<response" in text and ("panos" in text or "palo alto" in text or "status=\"error\"" in text):
            return {
                "status": "detected",
                "port": port,
                "status_code": resp.status_code,
            }
    except requests.RequestException:
        return None
    return None


def _checkpoint_management_probe(host: str, port: int, timeout_seconds: int) -> dict[str, Any] | None:
    try:
        resp = requests.post(
            f"https://{host}:{port}/web_api/show-api-versions",
            json={},
            verify=False,
            timeout=timeout_seconds,
        )
        payload = resp.json() if resp.headers.get("Content-Type", "").startswith("application/json") else {}
        if "supported-versions" in payload or payload.get("code"):
            return {
                "status": "detected",
                "port": port,
                "status_code": resp.status_code,
            }
    except (ValueError, requests.RequestException):
        return None
    return None


def _classify_target(target: PreparedTarget, facts: dict[str, Any]) -> tuple[list[str], str | None, list[str]]:
    suggestions: list[str] = []
    reasons: list[str] = []

    tokens = _tokenize_target(target)
    http_fingerprints = " ".join(
        f"{entry.get('server', '')} {entry.get('body_snippet', '')}".lower()
        for entry in facts.get("http") or []
    )
    open_ports = set(facts.get("open_ports") or [])
    redis_probe = facts.get("redis") or {}
    postgres_probe = facts.get("postgres") or {}
    ldap_probe = facts.get("ldap") or {}
    snmp_probe = facts.get("snmp_probe") or {}
    management_apis = facts.get("management_apis") or {}

    def add(candidate: str, reason: str) -> None:
        if candidate not in suggestions:
            suggestions.append(candidate)
            reasons.append(reason)

    if target.declared_connector_type:
        add(target.declared_connector_type, f"inventory declared connector_type={target.declared_connector_type}")

    token_rules = {
        "cisco-ftd": {"ftd", "firepower"},
        "fortinet": {"forti", "fortigate"},
        "paloalto": {"palo", "panos", "panorama"},
        "checkpoint": {"checkpoint", "sec-gw", "secgw", "gaia"},
        "juniper": {"juniper", "junos"},
        "cisco-nxos": {"nxos", "nexus"},
        "cisco-router": {"router", "wan"},
        "vyos": {"vyos"},
        "cisco-wlc": {"wlc", "wireless-controller"},
        "aruba-ap": {"aruba-ap", "access-point", "campus-ap", "wifi-ap"},
        "aruba-switch": {"aruba-switch", "switch", "access-switch"},
        "grafana": {"grafana"},
        "prometheus": {"prometheus", "prom"},
        "elasticsearch": {"elastic", "elasticsearch"},
        "nginx": {"nginx", "web-gw", "web"},
        "postgres": {"postgres", "pgsql", "database", "db"},
        "redis": {"redis", "cache"},
        "openldap": {"ldap", "openldap"},
        "snort": {"snort", "ids"},
        "strongswan": {"strongswan", "vpn"},
    }

    for candidate, expected_tokens in token_rules.items():
        if tokens & expected_tokens:
            add(candidate, f"name or metadata tokens matched {candidate}")

    http_rules = {
        "grafana": ("grafana",),
        "prometheus": ("prometheus",),
        "elasticsearch": ("elasticsearch",),
        "nginx": ("nginx",),
        "fortinet": ("fortinet", "fortigate"),
        "paloalto": ("palo alto", "pan-os", "panorama"),
        "checkpoint": ("checkpoint",),
    }
    for candidate, signatures in http_rules.items():
        if any(signature in http_fingerprints for signature in signatures):
            add(candidate, f"HTTP fingerprint matched {candidate}")

    if ldap_probe.get("status") == "detected":
        add("openldap", "LDAP bind probe succeeded")

    if snmp_probe.get("status") == "detected":
        snmp_text = str(snmp_probe.get("sys_descr") or "").lower()
        snmp_rules = {
            "fortinet": ("fortigate", "fortinet"),
            "paloalto": ("palo alto", "panos", "pan-os"),
            "checkpoint": ("checkpoint", "gaia"),
            "cisco": ("cisco", "ios xe", "ios"),
            "cisco-nxos": ("nx-os", "nexus"),
            "juniper": ("junos", "juniper"),
            "aruba-switch": ("aruba",),
        }
        for candidate, signatures in snmp_rules.items():
            if any(signature in snmp_text for signature in signatures):
                add(candidate, f"SNMP sysDescr matched {candidate}")

    for candidate, probe in management_apis.items():
        if probe.get("status") == "detected":
            add(candidate, f"{candidate} management API probe succeeded")

    if redis_probe.get("status") == "detected":
        add("redis", "Redis protocol probe succeeded")

    if postgres_probe.get("status") == "detected":
        add("postgres", "PostgreSQL protocol probe succeeded")

    port_rules = {
        3000: "grafana",
        9090: "prometheus",
        9200: "elasticsearch",
    }
    for port, candidate in port_rules.items():
        if port in open_ports and candidate not in suggestions:
            add(candidate, f"default service port {port} is reachable")

    if SSH_PORT in open_ports and not suggestions:
        suggestions.extend([
            "cisco",
            "juniper",
            "cisco-router",
            "cisco-ftd",
            "aruba-switch",
            "vyos",
        ])
        reasons.append("SSH is reachable but no vendor-specific fingerprint matched")

    if not suggestions and open_ports & HTTP_PORTS:
        suggestions.extend(["nginx", "grafana", "prometheus", "elasticsearch"])
        reasons.append("HTTP(S) is reachable but response did not expose a strong fingerprint")

    if not suggestions:
        reasons.append("No classification rule matched yet")

    selected = suggestions[0] if len(suggestions) == 1 else None
    return suggestions, selected, reasons


def _tokenize_target(target: PreparedTarget) -> set[str]:
    values = [target.host, target.name_hint or "", target.declared_connector_type or ""]
    if target.metadata:
        values.extend(str(value) for value in target.metadata.values())

    normalized = " ".join(values).lower()
    separators = ["-", "_", ".", "/", ":", "(", ")"]
    for separator in separators:
        normalized = normalized.replace(separator, " ")
    return {token for token in normalized.split() if token}


def _build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(item["status"] for item in results)
    selected_types = Counter(item["selected_connector_type"] for item in results if item["selected_connector_type"])
    reachable = statuses.get("reachable", 0)
    return {
        "total_targets": len(results),
        "reachable_targets": reachable,
        "unreachable_targets": statuses.get("unreachable", 0),
        "selected_connector_types": dict(selected_types),
        "suggested_connector_types": dict(
            Counter(candidate for item in results for candidate in item.get("suggested_connector_types", []))
        ),
    }


def _build_evidence(
    open_ports: list[int],
    redis_probe: dict[str, Any] | None,
    postgres_probe: dict[str, Any] | None,
    ldap_probe: dict[str, Any] | None,
    snmp_probe: dict[str, Any] | None,
    management_api_probes: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    service_detected = any(
        probe and probe.get("status") == "detected"
        for probe in (redis_probe, postgres_probe, ldap_probe)
    )
    api_manageable = any(probe.get("status") == "detected" for probe in management_api_probes.values())
    snmp_identified = bool(snmp_probe and snmp_probe.get("status") == "detected")
    ssh_reachable = SSH_PORT in open_ports
    reachable = bool(open_ports) or snmp_identified
    return {
        "reachable": reachable,
        "service_detected": service_detected,
        "ssh_manageable": ssh_reachable,
        "api_manageable": api_manageable,
        "snmp_identified": snmp_identified,
    }


def _encode_length(length: int) -> bytes:
    if length < 0x80:
        return bytes([length])
    raw = length.to_bytes((length.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(raw)]) + raw


def _wrap_tlv(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + _encode_length(len(value)) + value


def _encode_integer(value: int) -> bytes:
    if value == 0:
        return _wrap_tlv(0x02, b"\x00")
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big", signed=False)
    if raw[0] & 0x80:
        raw = b"\x00" + raw
    return _wrap_tlv(0x02, raw)


def _encode_octet_string(value: bytes | str) -> bytes:
    payload = value.encode() if isinstance(value, str) else value
    return _wrap_tlv(0x04, payload)


def _encode_null() -> bytes:
    return _wrap_tlv(0x05, b"")


def _encode_oid(oid: str) -> bytes:
    parts = [int(part) for part in oid.split(".")]
    first = 40 * parts[0] + parts[1]
    encoded = bytearray([first])
    for part in parts[2:]:
        stack = [part & 0x7F]
        part >>= 7
        while part:
            stack.append(0x80 | (part & 0x7F))
            part >>= 7
        encoded.extend(reversed(stack))
    return _wrap_tlv(0x06, bytes(encoded))


def _read_tlv(data: bytes, offset: int = 0) -> tuple[int, bytes, int]:
    tag = data[offset]
    offset += 1
    first_len = data[offset]
    offset += 1
    if first_len & 0x80:
        size = first_len & 0x7F
        length = int.from_bytes(data[offset:offset + size], "big")
        offset += size
    else:
        length = first_len
    end = offset + length
    return tag, data[offset:end], end


def _decode_integer(value: bytes) -> int:
    return int.from_bytes(value, "big", signed=bool(value and value[0] & 0x80))


def _ldap_bind_request() -> bytes:
    bind_request = _wrap_tlv(
        0x60,
        _encode_integer(3) + _encode_octet_string(b"") + _wrap_tlv(0x80, b""),
    )
    return _wrap_tlv(0x30, _encode_integer(1) + bind_request)


def _parse_ldap_bind_response(data: bytes) -> dict[str, Any] | None:
    try:
        _, payload, _ = _read_tlv(data, 0)
        _, _, offset = _read_tlv(payload, 0)
        tag, bind_response, _ = _read_tlv(payload, offset)
        if tag != 0x61:
            return None
        _, result_code_raw, inner = _read_tlv(bind_response, 0)
        _, matched_dn_raw, inner = _read_tlv(bind_response, inner)
        _, diagnostic_raw, _ = _read_tlv(bind_response, inner)
        return {
            "result_code": _decode_integer(result_code_raw),
            "matched_dn": matched_dn_raw.decode(errors="ignore"),
            "diagnostic_message": diagnostic_raw.decode(errors="ignore"),
        }
    except Exception:
        return None


def _snmp_sysdescr_request() -> bytes:
    varbind = _wrap_tlv(0x30, _encode_oid("1.3.6.1.2.1.1.1.0") + _encode_null())
    varbind_list = _wrap_tlv(0x30, varbind)
    pdu = _wrap_tlv(0xA0, _encode_integer(1) + _encode_integer(0) + _encode_integer(0) + varbind_list)
    return _wrap_tlv(0x30, _encode_integer(1) + _encode_octet_string("public") + pdu)


def _parse_snmp_response(data: bytes) -> dict[str, Any] | None:
    try:
        _, payload, _ = _read_tlv(data, 0)
        _, _, offset = _read_tlv(payload, 0)
        _, community_raw, offset = _read_tlv(payload, offset)
        _, pdu_payload, _ = _read_tlv(payload, offset)
        _, _, inner = _read_tlv(pdu_payload, 0)
        _, error_status_raw, inner = _read_tlv(pdu_payload, inner)
        _, _, inner = _read_tlv(pdu_payload, inner)
        _, varbind_list_payload, _ = _read_tlv(pdu_payload, inner)
        _, varbind_payload, _ = _read_tlv(varbind_list_payload, 0)
        _, _, value_offset = _read_tlv(varbind_payload, 0)
        value_tag, value_raw, _ = _read_tlv(varbind_payload, value_offset)

        result: dict[str, Any] = {
            "status": "detected",
            "community": community_raw.decode(errors="ignore"),
            "error_status": _decode_integer(error_status_raw),
        }
        if value_tag == 0x04:
            result["sys_descr"] = value_raw.decode(errors="ignore")
        elif value_tag == 0x02:
            result["value_int"] = _decode_integer(value_raw)
        else:
            result["raw_value"] = value_raw.hex()
        return result
    except Exception:
        return None


def _normalize_bootstrap_selections(
    session_results: list[DiscoveryResult],
    raw_items: list[dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    if not raw_items:
        return {}

    known_result_ids = {result.id for result in session_results}
    selections: dict[int, dict[str, Any]] = {}
    for raw_item in raw_items:
        result_id = int(raw_item.get("result_id"))
        if result_id not in known_result_ids:
            raise ValueError(f"Discovery result {result_id} does not belong to session")
        if result_id in selections:
            raise ValueError(f"Discovery result {result_id} was selected more than once")

        connector_type = raw_item.get("connector_type") or None
        if connector_type is not None and connector_type not in connector_service.CONNECTOR_CLASSES:
            raise ValueError(f"Unknown connector type override: {connector_type}")

        run_sync = raw_item.get("run_sync")
        selections[result_id] = {
            "connector_type": connector_type,
            "run_sync": None if run_sync is None else bool(run_sync),
        }
    return selections


async def _bootstrap_result(
    db: AsyncSession,
    result: DiscoveryResult,
    existing_by_host: dict[str, Connector],
    *,
    connector_defaults: dict[str, dict[str, Any]],
    default_config: dict[str, Any],
    sync_mode: str,
    sync_interval_minutes: int,
    run_sync: bool,
    allow_ambiguous: bool,
    on_existing: str,
    connector_type_override: str | None,
    run_sync_override: bool | None,
) -> dict[str, Any]:
    host = result.host
    connector_type = connector_type_override or _resolve_connector_type(result, allow_ambiguous)
    should_run_sync = run_sync if run_sync_override is None else run_sync_override
    detail: dict[str, Any] = {}

    if connector_type_override:
        detail["connector_type_override"] = connector_type_override

    if result.status != "reachable":
        result.preflight_status = "skipped"
        result.bootstrap_status = "skipped_unreachable"
        result.bootstrap_detail = {"reason": "target is not reachable from discovery probes"}
        await db.flush()
        return _bootstrap_item_payload(result, connector_type, result.bootstrap_detail or {})

    if connector_type is None:
        result.preflight_status = "skipped"
        result.bootstrap_status = "skipped_ambiguous"
        result.bootstrap_detail = {"reason": "unable to select a single connector type", "suggested_connector_types": result.suggested_connector_types}
        await db.flush()
        return _bootstrap_item_payload(result, connector_type, result.bootstrap_detail or {})

    config = _build_connector_config(host, connector_type, default_config, connector_defaults)
    preflight = await _preflight_connector(connector_type, config, result.facts)
    result.preflight_status = preflight["status"]
    detail["preflight"] = preflight

    if preflight["status"] != "passed":
        result.bootstrap_status = "error"
        result.bootstrap_detail = detail
        result.error = preflight.get("message")
        await db.flush()
        return _bootstrap_item_payload(result, connector_type, detail)

    existing = existing_by_host.get(host)
    if existing is not None:
        result.connector_id = existing.id
        result.connector_name = existing.name
        if on_existing == "resync" and should_run_sync:
            sync_result = await connector_service.sync_connector(db, existing.id)
            detail["sync"] = sync_result
            result.bootstrap_status = "synced" if sync_result.get("status") == "synced" else "error"
        else:
            result.bootstrap_status = "skipped_existing"
            detail["reason"] = "connector for host already exists"
        result.bootstrap_detail = detail
        await db.flush()
        return _bootstrap_item_payload(result, connector_type, detail)

    connector_name = _default_connector_name(result, connector_type)
    created = await connector_service.create_connector(
        db,
        {
            "name": connector_name,
            "connector_type": connector_type,
            "config": config,
            "sync_mode": sync_mode,
            "sync_interval_minutes": sync_interval_minutes,
        },
    )
    result.connector_id = created.id
    result.connector_name = created.name
    existing_by_host[host] = created

    detail["connector"] = {"id": created.id, "name": created.name}
    if should_run_sync:
        sync_result = await connector_service.sync_connector(db, created.id)
        detail["sync"] = sync_result
        result.bootstrap_status = "synced" if sync_result.get("status") == "synced" else "error"
        if result.bootstrap_status == "error":
            result.error = connector_service._extract_error_message(sync_result) or sync_result.get("error")
    else:
        result.bootstrap_status = "created"
    result.bootstrap_detail = detail
    await db.flush()
    return _bootstrap_item_payload(result, connector_type, detail)


def _bootstrap_item_payload(result: DiscoveryResult, connector_type: str | None, detail: dict[str, Any]) -> dict[str, Any]:
    return {
        "result_id": result.id,
        "host": result.host,
        "connector_type": connector_type,
        "connector_id": result.connector_id,
        "connector_name": result.connector_name,
        "preflight_status": result.preflight_status,
        "bootstrap_status": result.bootstrap_status,
        "detail": detail,
    }


def _resolve_connector_type(result: DiscoveryResult, allow_ambiguous: bool) -> str | None:
    if result.selected_connector_type:
        return result.selected_connector_type
    suggestions = result.suggested_connector_types or []
    if len(suggestions) == 1:
        return suggestions[0]
    if allow_ambiguous and suggestions:
        return suggestions[0]
    return None


def _build_connector_config(
    host: str,
    connector_type: str,
    default_config: dict[str, Any],
    connector_defaults: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    config: dict[str, Any] = {"host": host}
    config.update(default_config)
    config.update(connector_defaults.get(connector_type, {}))
    config["host"] = host
    return config


def _default_connector_name(result: DiscoveryResult, connector_type: str) -> str:
    if result.name_hint:
        return f"{result.name_hint} ({connector_type})"
    return f"{result.host} ({connector_type})"


async def _preflight_connector(connector_type: str, config: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    open_ports = set(facts.get("open_ports") or [])

    if connector_type in SSH_CONNECTOR_TYPES:
        if 22 not in open_ports:
            return {"status": "failed", "message": "SSH port 22 was not discovered as reachable"}
        if not config.get("username") or not config.get("password"):
            return {"status": "failed", "message": "Missing username/password for SSH preflight"}
        return await asyncio.to_thread(_ssh_preflight, config)

    if connector_type == "fortinet":
        if not config.get("api_token"):
            return {"status": "failed", "message": "Missing api_token for Fortinet preflight"}
        return await asyncio.to_thread(_fortinet_preflight, config)

    if connector_type == "paloalto":
        if not config.get("api_key"):
            return {"status": "failed", "message": "Missing api_key for Palo Alto preflight"}
        return await asyncio.to_thread(_paloalto_preflight, config)

    if connector_type == "checkpoint":
        if not config.get("username") or not config.get("password"):
            return {"status": "failed", "message": "Missing username/password for Check Point preflight"}
        return await asyncio.to_thread(_checkpoint_preflight, config)

    return {"status": "passed", "message": "No preflight implemented for connector type; accepted"}


def _ssh_preflight(config: dict[str, Any]) -> dict[str, Any]:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            config["host"],
            username=config["username"],
            password=config["password"],
            timeout=10,
            banner_timeout=15,
            auth_timeout=15,
        )
        return {"status": "passed", "message": "SSH authentication succeeded"}
    except Exception as exc:
        return {"status": "failed", "message": str(exc)}
    finally:
        client.close()


def _fortinet_preflight(config: dict[str, Any]) -> dict[str, Any]:
    verify_ssl = bool(config.get("verify_ssl", False))
    resp = requests.get(
        f"https://{config['host']}/api/v2/monitor/system/status",
        headers={"Authorization": f"Bearer {config['api_token']}"},
        verify=verify_ssl,
        timeout=15,
    )
    if resp.ok:
        return {"status": "passed", "message": "Fortinet API authentication succeeded"}
    return {"status": "failed", "message": f"Fortinet API returned {resp.status_code}"}


def _paloalto_preflight(config: dict[str, Any]) -> dict[str, Any]:
    verify_ssl = bool(config.get("verify_ssl", False))
    resp = requests.get(
        f"https://{config['host']}/api/?type=op&cmd=<show><system><info></info></system></show>&key={config['api_key']}",
        verify=verify_ssl,
        timeout=15,
    )
    if resp.ok and "<response status=\"success\"" in resp.text:
        return {"status": "passed", "message": "Palo Alto API authentication succeeded"}
    return {"status": "failed", "message": f"Palo Alto API returned {resp.status_code}"}


def _checkpoint_preflight(config: dict[str, Any]) -> dict[str, Any]:
    verify_ssl = bool(config.get("verify_ssl", False))
    payload = {"user": config["username"], "password": config["password"]}
    if config.get("domain"):
        payload["domain"] = config["domain"]
    resp = requests.post(
        f"https://{config['host']}/web_api/login",
        json=payload,
        verify=verify_ssl,
        timeout=15,
    )
    if resp.ok and resp.json().get("sid"):
        return {"status": "passed", "message": "Check Point API authentication succeeded"}
    return {"status": "failed", "message": f"Check Point API returned {resp.status_code}"}