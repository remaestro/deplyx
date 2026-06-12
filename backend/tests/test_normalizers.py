"""Tests unitaires pour le module normalizers (isolé, sans base de données)."""

from __future__ import annotations

import pytest

from app.connectors_v2.normalizers import (
    safe_id,
    hash_id,
    is_ip_interface_brief_command,
    extract_system_info,
    parse_interfaces_raw,
    normalize_interfaces,
    merge_interfaces,
    parse_ip_int_brief,
    normalize_routes,
    normalize_vlans,
    normalize_bgp,
    normalize_redundancy,
    normalize_etherchannel,
    normalize_redundancy_general,
    normalize_neighbors,
    parse_acl_bindings,
    normalize_access_lists,
    normalize_http_service,
    normalize_arp,
    parse_ftd_network,
)


# ── safe_id ─────────────────────────────────────────────────────────

class TestSafeId:
    def test_basic(self):
        assert safe_id("Foo-Bar_123!!") == "Foo-Bar_123"

    def test_empty(self):
        assert safe_id("") == "unknown"

    def test_whitespace(self):
        assert safe_id("  hello world  ") == "hello-world"

    def test_special_chars(self):
        assert safe_id("a/b:c,d[e]f") == "a-b-c-d-e-f"

    def test_only_special(self):
        assert safe_id("!!!???") == "unknown"


# ── hash_id ─────────────────────────────────────────────────────────

class TestHashId:
    def test_stable(self):
        assert hash_id("test", "DEV") == "DEV-098F6BCD"

    def test_default_prefix(self):
        h = hash_id("hello")
        assert h.startswith("DEV-")


# ── is_ip_interface_brief_command ──────────────────────────────────

class TestIsIpInterfaceBrief:
    def test_positive(self):
        assert is_ip_interface_brief_command("show ip interface brief")
        assert is_ip_interface_brief_command("show ip int brief")
        assert is_ip_interface_brief_command("  SHOW IP INT BRIEF  ")

    def test_negative(self):
        assert not is_ip_interface_brief_command("show interfaces")
        assert not is_ip_interface_brief_command("show running-config")
        assert not is_ip_interface_brief_command("")


# ── extract_system_info ────────────────────────────────────────────

class TestExtractSystemInfo:
    def test_cisco_show_version(self):
        output = """\
Cisco IOS Software, C3850 Software (C3850-UNIVERSALK9-M), Version 16.12.3
Copyright (c) 1986-2020 by Cisco Systems, Inc.
switch1 uptime is 2 weeks, 3 days, 10 hours
Processor board ID FOC1234ABCD
"""
        result = extract_system_info(output, {})
        assert result["hostname"] == "switch1"
        assert result["serial"] == "FOC1234ABCD"
        assert result["os_version"] == "16.12.3"

    def test_hostname_format(self):
        output = "hostname fw-dc1\n"
        result = extract_system_info(output, {})
        assert result["hostname"] == "fw-dc1"

    def test_no_match_returns_original(self):
        result = extract_system_info("garbage output", {"existing": "val"})
        assert result["existing"] == "val"

    def test_model_extraction(self):
        output = "Model number : ISR4331/K9 Version 17.3"
        result = extract_system_info(output, {"hostname": "r1"})
        assert result["model"] == "ISR4331/K9"


# ── parse_interfaces_raw ───────────────────────────────────────────

class TestParseInterfacesRaw:
    def test_cisco_style(self):
        raw = """\
GigabitEthernet0/1 is up, line protocol is up
  Internet address is 10.0.0.1/24
GigabitEthernet0/2 is administratively down, line protocol is down
  Internet address is 10.0.0.2/24
"""
        ifaces = parse_interfaces_raw(raw)
        assert len(ifaces) == 2
        assert ifaces[0]["name"] == "GigabitEthernet0/1"
        assert ifaces[0]["status"] == "up"
        assert ifaces[0]["ip"] == "10.0.0.1"
        assert ifaces[0]["mask"] == "24"
        assert ifaces[1]["name"] == "GigabitEthernet0/2"
        assert ifaces[1]["status"] == "administratively down"

    def test_empty(self):
        assert parse_interfaces_raw("") == []

    def test_no_ip(self):
        raw = "FastEthernet0/0 is up, line protocol is up\n"
        ifaces = parse_interfaces_raw(raw)
        assert len(ifaces) == 1
        assert ifaces[0]["ip"] == ""


# ── normalize_interfaces ───────────────────────────────────────────

class TestNormalizeInterfaces:
    def test_from_textfsm(self):
        parsed = [
            {"interface": "Gi0/1", "status": "up", "ip_address": "192.168.1.1", "subnet": "24"},
            {"interface": "Gi0/2", "status": "down", "ip_address": "", "subnet": ""},
        ]
        result = normalize_interfaces(parsed, "")
        assert len(result) == 2
        assert result[0]["name"] == "Gi0/1"
        assert result[0]["status"] == "up"
        assert result[0]["ip"] == "192.168.1.1"

    def test_with_metrics(self):
        parsed = [
            {"interface": "Gi0/1", "input_errors": "15", "output_errors": "3"},
        ]
        result = normalize_interfaces(parsed, "")
        assert result[0]["input_errors"] == 15
        assert result[0]["output_errors"] == 3

    def test_fallback_to_raw(self):
        parsed = [{"raw": "unparseable"}]
        result = normalize_interfaces(parsed, "")
        # raw fallback renvoie [] car rien de parsable
        assert result == []


# ── merge_interfaces ───────────────────────────────────────────────

class TestMergeInterfaces:
    def test_merge(self):
        old = [{"name": "Gi0/1", "status": "up", "ip": "", "mask": ""}]
        new = [{"name": "Gi0/1", "status": "up", "ip": "10.0.0.1", "mask": "24"}]
        merged = merge_interfaces(old, new)
        assert len(merged) == 1
        assert merged[0]["ip"] == "10.0.0.1"

    def test_deduplicate(self):
        a = [{"name": "Gi0/1", "status": "up", "ip": "", "mask": ""}]
        b = [{"name": "Gi0/1", "status": "up", "ip": "10.0.0.1", "mask": "24"}]
        assert len(merge_interfaces(a, b)) == 1


# ── parse_ip_int_brief ─────────────────────────────────────────────

class TestParseIpIntBrief:
    def test_parse(self):
        raw = """\
Interface              IP-Address      OK?    Method Status    Protocol
GigabitEthernet0/1     10.0.0.1        YES    unset  up          up
GigabitEthernet0/2     unassigned      YES    unset  down        down
"""
        result = parse_ip_int_brief(raw, [])
        assert len(result) == 1
        assert result[0]["name"] == "GigabitEthernet0/1"
        assert result[0]["status"] == "up"


# ── normalize_routes ───────────────────────────────────────────────

class TestNormalizeRoutes:
    def test_from_textfsm(self):
        parsed = [{"network": "10.1.0.0/16"}, {"network": "10.2.0.0/16"}]
        assert normalize_routes(parsed, "") == parsed

    def test_fallback_raw(self):
        raw = "S   10.1.0.0/16 [1/0] via 192.168.1.1\n"
        parsed = [{"raw": raw}]
        result = normalize_routes(parsed, raw)
        assert len(result) == 1
        assert result[0]["network"] == "10.1.0.0/16"

    def test_empty(self):
        assert normalize_routes([], "") == []


# ── normalize_vlans ────────────────────────────────────────────────

class TestNormalizeVlans:
    def test_from_textfsm(self):
        parsed = [
            {"vlan_id": "100", "name": "Users", "interfaces": "Gi0/1,Gi0/2"},
        ]
        result = normalize_vlans(parsed, "")
        assert len(result) == 1
        assert result[0]["vlan_id"] == "100"
        assert "Gi0/1" in result[0]["interfaces"]

    def test_fallback_raw(self):
        raw = "100   Users\n200   Guests\n"
        parsed = [{"raw": raw}]
        result = normalize_vlans(parsed, raw)
        assert len(result) == 2


# ── normalize_bgp ──────────────────────────────────────────────────

class TestNormalizeBgp:
    def test_from_textfsm(self):
        parsed = [{"neighbor": "10.0.0.1"}]
        assert normalize_bgp(parsed, "") == parsed

    def test_fallback_raw(self):
        raw = "10.0.0.1      4 65001    10   5000    3000 00:01:23 Established\n"
        parsed = [{"raw": raw}]
        result = normalize_bgp(parsed, raw)
        assert len(result) == 1
        assert result[0]["neighbor"] == "10.0.0.1"


# ── normalize_redundancy ───────────────────────────────────────────

class TestNormalizeRedundancy:
    def test_hsrp_groups(self):
        parsed = [
            {"group": "10", "state": "active", "virtual_ip": "10.0.0.254",
             "priority": "110", "standby_router": "10.0.0.2"},
        ]
        result = normalize_redundancy(parsed, "hsrp", "")
        assert result["has_redundancy"] is True
        assert len(result["groups"]) == 1
        assert result["groups"][0]["group"] == "10"

    def test_no_active_standby(self):
        parsed = [{"group": "10", "state": "active", "standby_router": "unknown"}]
        result = normalize_redundancy(parsed, "hsrp", "")
        assert result["has_redundancy"] is False


# ── normalize_etherchannel ─────────────────────────────────────────

class TestNormalizeEtherchannel:
    def test_channels(self):
        parsed = [{"channel": "1", "ports": "Gi0/1,Gi0/2", "protocol": "lacp", "status": "up"}]
        result = normalize_etherchannel(parsed, "")
        assert result["has_redundancy"] is True
        assert len(result["channels"]) == 1


# ── normalize_neighbors ────────────────────────────────────────────

class TestNormalizeNeighbors:
    def test_cdp(self):
        parsed = [
            {"neighbor_name": "switch1.example.com", "local_interface": "Gi0/1",
             "neighbor_interface": "Gi0/2", "platform": "cisco WS-C3850",
             "mgmt_address": "10.0.0.2"},
        ]
        result = normalize_neighbors(parsed, "cdp")
        assert len(result) == 1
        assert result[0]["hostname"] == "switch1.example.com"
        assert result[0]["protocol"] == "cdp"

    def test_empty(self):
        assert normalize_neighbors([], "cdp") == []


# ── parse_acl_bindings ─────────────────────────────────────────────

class TestParseAclBindings:
    def test_parse(self):
        raw = """\
GigabitEthernet0/1 is up, line protocol is up
  Inbound  access list is 100
  Outgoing access list is 110
"""
        result = parse_acl_bindings(raw)
        assert len(result) == 2
        assert result[0] == {"interface": "GigabitEthernet0/1", "direction": "in", "acl": "100"}
        assert result[1] == {"interface": "GigabitEthernet0/1", "direction": "out", "acl": "110"}

    def test_not_set(self):
        raw = "GigabitEthernet0/1 is up\n  Inbound  access list is not set\n"
        result = parse_acl_bindings(raw)
        assert len(result) == 0


# ── normalize_access_lists ─────────────────────────────────────────

class TestNormalizeAccessLists:
    def test_from_textfsm(self):
        parsed = [{"id": "100", "name": "TEST_ACL", "type": "ip", "entries": []}]
        result = normalize_access_lists(parsed, "")
        assert len(result) == 1
        assert result[0]["id"] == "100"

    def test_fallback_raw(self):
        raw = "Extended IP access list 100\n"
        parsed = [{"raw": raw}]
        result = normalize_access_lists(parsed, raw)
        assert len(result) == 1


# ── normalize_http_service ─────────────────────────────────────────

class TestNormalizeHttpService:
    def test_enabled(self):
        parsed = [{"status": "enabled", "port": "8080"}]
        result = normalize_http_service("", parsed)
        assert len(result) == 1
        assert result[0]["enabled"] is True
        assert result[0]["port"] == 8080

    def test_disabled(self):
        parsed = [{"status": "disabled"}]
        result = normalize_http_service("", parsed)
        assert result[0]["enabled"] is False

    def test_fallback_raw(self):
        raw = "HTTP server status: enabled\nHTTP server port: 80\n"
        result = normalize_http_service(raw, [{"raw": raw}])
        assert result[0]["enabled"] is True
        assert result[0]["port"] == 80


# ── normalize_arp ──────────────────────────────────────────────────

class TestNormalizeArp:
    def test_from_textfsm(self):
        parsed = [
            {"address": "10.0.0.1", "mac": "aaaa.bbbb.cccc", "interface": "Gi0/1", "type": "dynamic"},
        ]
        result = normalize_arp(parsed, "")
        assert len(result) == 1
        assert result[0]["ip"] == "10.0.0.1"

    def test_deduplicate(self):
        parsed = [
            {"address": "10.0.0.1", "mac": "aaaa.bbbb.cccc", "interface": "Gi0/1"},
            {"address": "10.0.0.1", "mac": "aaaa.bbbb.cccc", "interface": "Gi0/1"},
        ]
        result = normalize_arp(parsed, "")
        assert len(result) == 1

    def test_fallback_raw(self):
        raw = "Internet  10.0.0.1         -    aaaa.bbbb.cccc  ARPA   Gi0/1\n"
        parsed = [{"raw": raw}]
        result = normalize_arp(parsed, raw)
        assert len(result) == 1


# ── parse_ftd_network ──────────────────────────────────────────────

class TestParseFtdNetwork:
    def test_hostname_and_interfaces(self):
        output = """\
Hostname : ftd-firewall
============[ inside ]============
Address : 10.0.1.1
============[ outside ]============
Address : 10.0.0.1
"""
        result = parse_ftd_network(output, {})
        assert result["hostname"] == "ftd-firewall"
        assert len(result["interfaces"]) == 2
        assert result["interfaces"][0]["name"] == "inside"
        assert result["interfaces"][0]["ip"] == "10.0.1.1"
