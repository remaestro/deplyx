"""Pre-change live validation service.

Executes REAL commands on the target device (via its connector credentials)
before a change is approved, to replace hypothetical warnings with hard
evidence: next-hop reachability, ARP state, route table before/after,
route recursion, and a current-vs-proposed path comparison.

Currently supports static route changes (``ip route <net> <mask> <nh>``
detected in the execution plan). Other change kinds return
``{"supported": False}`` and the analysis falls back to graph+LLM only.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.graph.neo4j_client import neo4j_client
from app.models.connector import Connector
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Total wall-clock budget for all live commands (seconds)
VALIDATION_TIMEOUT = 90

_ROUTE_LINE = re.compile(
    r"(?:^|\n)\s*(?:\d+[\.\)]\s*)?(no\s+)?ip route\s+"
    r"(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)",
    re.IGNORECASE,
)


async def run_prechange_validation(
    db: AsyncSession,
    change: Any,
    target_node_ids: list[str],
) -> dict[str, Any] | None:
    """Run live pre-change validations for a change. Never raises."""
    try:
        return await asyncio.wait_for(
            _run(db, change, target_node_ids), timeout=VALIDATION_TIMEOUT
        )
    except asyncio.TimeoutError:
        logger.warning("[PRECHANGE] validation timed out after %ds", VALIDATION_TIMEOUT)
        return {"supported": True, "error": f"Validation timed out after {VALIDATION_TIMEOUT}s", "checks": []}
    except Exception as exc:  # noqa: BLE001 — must never break the pipeline
        logger.warning("[PRECHANGE] validation failed: %s", exc)
        return {"supported": False, "reason": f"validation error: {exc}", "checks": []}


async def _run(db: AsyncSession, change: Any, target_node_ids: list[str]) -> dict[str, Any]:
    # ── 1. Parse the execution plan for a static route change ───────
    route = _parse_route_change(getattr(change, "execution_plan", "") or "")
    if not route:
        return {"supported": False, "reason": "no static route change detected in execution plan", "checks": []}

    # ── 2. Resolve the target device + its connector credentials ────
    device = await _find_target_device(target_node_ids)
    if not device:
        return {"supported": False, "reason": "target device not found in graph", "checks": []}

    connector = await _find_connector(db, device.get("ip", ""))
    if not connector:
        return {
            "supported": True,
            "device": device,
            "route_change": route,
            "checks": [_check("connector", "Device connector lookup", "skip",
                              f"No connector found for {device.get('ip')} — live validation skipped")],
            "error": "no connector credentials",
        }

    # ── 3. Run live commands over SSH (sync netmiko → thread) ───────
    cfg = connector.config or {}
    live = await asyncio.to_thread(
        _collect_live_data,
        host=cfg.get("host", device.get("ip", "")),
        username=cfg.get("username", ""),
        password=cfg.get("password", ""),
        route=route,
    )

    # ── 4. Build checks + path comparison from real outputs ─────────
    checks = _build_checks(route, live)
    path_cmp = _build_path_comparison(device, route, live)
    route_table = {
        "before": live.get("route_before_line") or live.get("route_before_raw", "").strip()[:400],
        "proposed": f"S    {route['cidr']} [1/0] via {route['new_next_hop']}",
    }

    return {
        "supported": True,
        "kind": "static_route",
        "device": device,
        "route_change": route,
        "checks": checks,
        "path_comparison": path_cmp,
        "route_table": route_table,
        "evidence_collected": live.get("evidence_collected", []),
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "error": live.get("error"),
    }


# ── Parsing helpers ─────────────────────────────────────────────────

def _parse_route_change(plan: str) -> dict[str, Any] | None:
    """Extract old/new static route from execution plan lines."""
    old_nh = new_nh = prefix = mask = None
    for m in _ROUTE_LINE.finditer(plan):
        negated, net, msk, nh = m.group(1), m.group(2), m.group(3), m.group(4)
        if negated:
            old_nh, prefix, mask = nh, net, msk
        else:
            new_nh, prefix, mask = nh, net, msk
    if not new_nh or not prefix:
        return None
    try:
        cidr = str(ipaddress.ip_network(f"{prefix}/{mask}", strict=False))
    except ValueError:
        cidr = f"{prefix}/{mask}"
    return {
        "prefix": prefix,
        "mask": mask,
        "cidr": cidr,
        "old_next_hop": old_nh,
        "new_next_hop": new_nh,
    }


async def _find_target_device(target_node_ids: list[str]) -> dict[str, Any] | None:
    for node_id in target_node_ids:
        props = await neo4j_client.get_node("Device", node_id)
        if props:
            return {
                "id": node_id,
                "hostname": props.get("hostname") or props.get("display_name") or node_id,
                "ip": props.get("ip", ""),
            }
    return None


async def _find_connector(db: AsyncSession, host: str) -> Connector | None:
    if not host:
        return None
    result = await db.execute(select(Connector))
    for conn in result.scalars().all():
        if (conn.config or {}).get("host") == host:
            return conn
    return None


# ── Live data collection (runs in a worker thread) ─────────────────

def _collect_live_data(*, host: str, username: str, password: str, route: dict[str, Any]) -> dict[str, Any]:
    from app.connectors_v2.transports.ssh import SSHTransport

    out: dict[str, Any] = {"evidence_collected": [], "error": None}
    transport = SSHTransport(host=host, username=username, password=password, device_type="cisco_ios")
    try:
        if not transport.connect():
            out["error"] = f"SSH connection to {host} failed"
            return out

        def run(cmd: str) -> str:
            try:
                return transport.send_command(cmd) or ""
            except Exception as exc:  # noqa: BLE001
                logger.warning("[PRECHANGE] '%s' failed: %s", cmd, exc)
                return ""

        prefix, new_nh, old_nh = route["prefix"], route["new_next_hop"], route["old_next_hop"]

        # Current route table entry
        raw = run(f"show ip route {prefix}")
        out["route_before_raw"] = raw
        out["route_before_line"] = _extract_route_line(raw, prefix)
        if raw:
            out["evidence_collected"].append("route_table")

        # New next-hop: ping (reachability + RTT)
        ping_new = run(f"ping {new_nh}")
        out["ping_new"] = _parse_ping(ping_new)
        out["ping_new_raw"] = _tail(ping_new)
        if ping_new:
            out["evidence_collected"].append("ping_new_next_hop")

        # Old next-hop: ping (for path delta baseline)
        if old_nh:
            ping_old = run(f"ping {old_nh}")
            out["ping_old"] = _parse_ping(ping_old)
            if ping_old:
                out["evidence_collected"].append("ping_old_next_hop")

        # ARP entry for the new next-hop
        arp = run(f"show ip arp {new_nh}")
        out["arp_new_raw"] = arp.strip()
        out["arp_new"] = _parse_arp(arp, new_nh)
        if arp:
            out["evidence_collected"].append("arp_table")

        # Route recursion: how is the new next-hop itself reached?
        rec = run(f"show ip route {new_nh}")
        out["recursion_raw"] = rec
        out["recursion"] = _parse_recursion(rec)
        if rec:
            out["evidence_collected"].append("route_recursion")

        # Egress interface state (if recursion revealed one)
        intf = out["recursion"].get("interface") if out.get("recursion") else None
        if intf:
            brief = run(f"show ip interface brief | include {intf}")
            out["intf_raw"] = brief.strip()
            out["intf_up"] = bool(re.search(r"\bup\s+up\b", brief))
            if brief:
                out["evidence_collected"].append("interface_status")
    finally:
        try:
            transport.disconnect()
        except Exception:  # noqa: BLE001
            pass
    return out


def _tail(text: str, lines: int = 3) -> str:
    rows = [r for r in text.strip().splitlines() if r.strip()]
    return "\n".join(rows[-lines:])


def _parse_ping(output: str) -> dict[str, Any]:
    res: dict[str, Any] = {"success_pct": None, "rtt_avg_ms": None}
    m = re.search(r"Success rate is (\d+) percent", output)
    if m:
        res["success_pct"] = int(m.group(1))
    m = re.search(r"round-trip min/avg/max = (\d+)/(\d+)/(\d+) ms", output)
    if m:
        res["rtt_avg_ms"] = int(m.group(2))
    return res


def _parse_arp(output: str, ip: str) -> dict[str, Any]:
    for line in output.splitlines():
        if ip in line:
            m = re.search(r"([0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4})", line, re.IGNORECASE)
            intf = line.split()[-1] if line.split() else ""
            return {"resolved": bool(m), "mac": m.group(1) if m else "", "interface": intf, "line": line.strip()}
    return {"resolved": False, "mac": "", "interface": "", "line": ""}


def _parse_recursion(output: str) -> dict[str, Any]:
    res: dict[str, Any] = {"resolved": False, "directly_connected": False, "interface": None}
    if re.search(r"directly connected", output, re.IGNORECASE):
        res["resolved"] = True
        res["directly_connected"] = True
        m = re.search(r"via\s+([A-Za-z]+[\d/\.]+)", output)
        if m:
            res["interface"] = m.group(1)
    elif re.search(r"Routing entry for", output, re.IGNORECASE):
        res["resolved"] = True
        m = re.search(r"via\s+(\d+\.\d+\.\d+\.\d+)(?:,\s*([A-Za-z]+[\d/\.]+))?", output)
        if m and m.group(2):
            res["interface"] = m.group(2)
    return res


def _extract_route_line(output: str, prefix: str) -> str:
    for line in output.splitlines():
        if "Routing entry for" in line or (prefix in line and re.match(r"\s*[SCOBDR*]", line)):
            return line.strip()
    return ""


# ── Check + path builders ───────────────────────────────────────────

def _check(name: str, label: str, status: str, detail: str = "", evidence: list[str] | None = None) -> dict[str, Any]:
    return {"name": name, "label": label, "status": status, "detail": detail, "evidence": evidence or []}


def _build_checks(route: dict[str, Any], live: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    new_nh = route["new_next_hop"]

    if live.get("error"):
        checks.append(_check("ssh", "SSH connectivity to device", "fail", live["error"]))
        return checks

    # 1. Current route present
    before = live.get("route_before_line", "")
    checks.append(_check(
        "current_route", f"Current route for {route['cidr']} present in RIB",
        "pass" if before else "warn",
        before or "No existing route found — change would ADD a route, not replace one",
        [before] if before else [],
    ))

    # 2. New next-hop reachability
    ping = live.get("ping_new") or {}
    pct, rtt = ping.get("success_pct"), ping.get("rtt_avg_ms")
    if pct is None:
        checks.append(_check("next_hop_reachable", f"New next-hop {new_nh} reachable", "skip", "ping output not available"))
    elif pct >= 60:
        detail = f"ICMP success {pct}%" + (f", RTT avg {rtt}ms" if rtt is not None else "")
        checks.append(_check("next_hop_reachable", f"New next-hop {new_nh} reachable from device", "pass", detail,
                             [live.get("ping_new_raw", "")]))
    else:
        checks.append(_check("next_hop_reachable", f"New next-hop {new_nh} UNREACHABLE from device", "fail",
                             f"ICMP success {pct}% — traffic to {route['cidr']} would be blackholed",
                             [live.get("ping_new_raw", "")]))

    # 3. ARP resolution
    arp = live.get("arp_new") or {}
    if arp.get("resolved"):
        checks.append(_check("arp_resolved", f"ARP entry for {new_nh} already learned", "pass",
                             f"MAC {arp['mac']} on {arp['interface']}", [arp.get("line", "")]))
    else:
        checks.append(_check("arp_resolved", f"ARP entry for {new_nh} not present", "warn",
                             "First packet will trigger ARP resolution — brief initial delay possible"))

    # 4. Route recursion
    rec = live.get("recursion") or {}
    if rec.get("directly_connected"):
        checks.append(_check("route_recursion", f"Next-hop {new_nh} is directly connected", "pass",
                             f"via {rec.get('interface') or 'connected interface'} — no recursion needed"))
    elif rec.get("resolved"):
        checks.append(_check("route_recursion", f"Route recursion for {new_nh} resolved", "pass",
                             f"reachable via {rec.get('interface') or 'recursive lookup'}"))
    else:
        checks.append(_check("route_recursion", f"No route to next-hop {new_nh} in RIB", "fail",
                             "The static route would be installed but unusable (recursive lookup fails)"))

    # 5. Egress interface state
    if live.get("intf_raw"):
        intf = (live.get("recursion") or {}).get("interface", "")
        checks.append(_check("egress_interface", f"Egress interface {intf} status", 
                             "pass" if live.get("intf_up") else "fail",
                             live["intf_raw"], [live["intf_raw"]]))

    return checks


def _build_path_comparison(device: dict[str, Any], route: dict[str, Any], live: dict[str, Any]) -> dict[str, Any]:
    hostname = device.get("hostname", "device")
    cidr = route["cidr"]
    net = None
    try:
        net = ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        pass

    def hop_count(nh: str | None) -> int | None:
        if not nh or not net:
            return None
        try:
            # Next-hop inside the destination subnet → direct delivery (1 hop)
            return 1 if ipaddress.ip_address(nh) in net else 2
        except ValueError:
            return None

    ping_old = live.get("ping_old") or {}
    ping_new = live.get("ping_new") or {}
    old_nh, new_nh = route.get("old_next_hop"), route["new_next_hop"]

    current = {
        "next_hop": old_nh,
        "hops": [hostname] + ([old_nh] if old_nh else []) + [cidr],
        "hop_count": hop_count(old_nh),
        "rtt_ms": ping_old.get("rtt_avg_ms"),
    }
    proposed = {
        "next_hop": new_nh,
        "hops": [hostname, new_nh, cidr] if hop_count(new_nh) != 1 else [hostname, f"{new_nh} ({cidr})"],
        "hop_count": hop_count(new_nh),
        "rtt_ms": ping_new.get("rtt_avg_ms"),
    }
    delta: dict[str, Any] = {}
    if current["hop_count"] and proposed["hop_count"]:
        delta["hop_count"] = f"{current['hop_count']} → {proposed['hop_count']}"
    if current["rtt_ms"] is not None and proposed["rtt_ms"] is not None:
        delta["rtt_ms"] = f"{current['rtt_ms']}ms → {proposed['rtt_ms']}ms"

    return {"current": current, "proposed": proposed, "delta": delta}
