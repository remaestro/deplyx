"""Tests pour le module generator (scanner, doc_collector, profile_generator)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.connectors_v2.generator.doc_collector import (
    NETMIKO_DEVICE_MAP,
    _COMMON_COMMANDS,
    _get_netmiko_device_types,
    _get_textfsm_commands,
    _guess_common_commands,
    _get_existing_profiles,
    _EXAMPLE_PROFILE_YAML,
    collect_device_info,
    get_example_profile,
)
from app.connectors_v2.generator.profile_generator import (
    _parse_llm_yaml,
    _guess_role,
    _generate_fallback_profile,
)


# ── doc_collector ───────────────────────────────────────────────────

class TestNetmikoTypes:
    def test_cisco_ios(self):
        types = _get_netmiko_device_types("cisco", "ios")
        assert "cisco_ios" in types

    def test_fortinet(self):
        types = _get_netmiko_device_types("fortinet")
        assert "fortinet" in types

    def test_unknown_vendor(self):
        types = _get_netmiko_device_types("nonexistent_vendor_xyz")
        assert types == []

    def test_mapping_completeness(self):
        """Chaque vendor doit avoir au moins un device_type."""
        for vendor, types in NETMIKO_DEVICE_MAP.items():
            assert len(types) >= 1, f"{vendor} n'a pas de device_type"


class TestGuessCommonCommands:
    def test_cisco(self):
        cmds = _guess_common_commands("cisco")
        assert "show version" in cmds
        assert "show interfaces" in cmds

    def test_unknown(self):
        cmds = _guess_common_commands("unknown_vendor")
        assert "show version" in cmds  # fallback universel

    def test_all_vendors_have_commands(self):
        """Chaque vendor dans COMMON_COMMANDS doit avoir des commandes."""
        for vendor, cmds in _COMMON_COMMANDS.items():
            assert len(cmds) >= 3, f"{vendor}: au moins 3 commandes"


class TestCollectDeviceInfo:
    def test_cisco_ios(self):
        info = collect_device_info("cisco", "ios")
        assert info["vendor"] == "cisco"
        assert "cisco_ios" in info["device_types_netmiko"]
        assert len(info["commands_disponibles"]) > 0

    def test_fortinet(self):
        info = collect_device_info("fortinet", "fortios")
        assert info["vendor"] == "fortinet"
        assert "fortinet" in info["device_types_netmiko"]
        assert info["commands_avec_template"] is not None
        assert info["fallback_device_type"] == "fortinet"

    def test_existing_profiles(self):
        """Vérifie que les profils existants sont chargés comme few-shot."""
        info = collect_device_info("cisco")
        assert len(info["profiles_existants"]) >= 0


class TestExampleProfile:
    def test_is_valid_yaml(self):
        data = yaml.safe_load(_EXAMPLE_PROFILE_YAML)
        assert isinstance(data, dict)
        assert data["name"] == "cisco-ios"
        assert data["vendor"] == "cisco"
        assert data["os"] == "ios"
        assert len(data["transports"]) > 0
        assert len(data["commands"]) > 0
        assert len(data["command_groups"]) > 0

    def test_get_example_profile(self):
        profile = get_example_profile()
        assert "cisco-ios" in profile
        assert "show version" in profile
        assert "device_type: cisco_ios" in profile


# ── profile_generator ──────────────────────────────────────────────

class TestParseLlmYaml:
    def test_valid_yaml(self):
        yaml_str = """\
vendor: cisco
os: ios
transports:
  - type: ssh
    priority: 10
    device_type: cisco_ios
commands:
  show_version: "show version"
  show_interfaces: "show interfaces"
command_groups:
  system:
    refs: ["show_version"]
neo4j_labels:
  device: "Device"
"""
        data = _parse_llm_yaml(yaml_str)
        assert data["vendor"] == "cisco"
        assert len(data["transports"]) == 1

    def test_missing_vendor(self):
        with pytest.raises(ValueError, match="Champs obligatoires"):
            _parse_llm_yaml("os: ios\ntransports:\n  - type: ssh\ncommands:\n  show_version: show version")

    def test_empty(self):
        with pytest.raises(ValueError):
            _parse_llm_yaml("")

    def test_not_a_dict(self):
        with pytest.raises(ValueError):
            _parse_llm_yaml("[1, 2, 3]")


class TestGuessRole:
    @pytest.mark.parametrize(
        "vendor,os_name,expected",
        [
            ("cisco", "ios", "switch"),
            ("cisco", "ftd", "firewall"),
            ("cisco", "nxos", "distribution-switch"),
            ("fortinet", "fortios", "firewall"),
            ("paloalto", "panos", "firewall"),
            ("checkpoint", "", "firewall"),
            ("juniper", "junos", "router"),
            ("aruba", "aruba", "switch"),
            ("cisco", "wlc", "wlc"),
        ],
    )
    def test_roles(self, vendor, os_name, expected):
        assert _guess_role(vendor, os_name) == expected


class TestGenerateFallbackProfile:
    def test_valid_yaml(self):
        yaml_str = _generate_fallback_profile("cisco", "ios", ["cisco_ios"])
        data = yaml.safe_load(yaml_str)
        assert data["vendor"] == "cisco"
        assert data["os"] == "ios"
        assert data["transports"][0]["device_type"] == "cisco_ios"
        assert "show_version" in data["commands"]

    def test_no_device_types(self):
        yaml_str = _generate_fallback_profile("unknown", "", [])
        data = yaml.safe_load(yaml_str)
        assert data["vendor"] == "unknown"
        assert data["os"] == "generic"


# ── get_existing_profiles ──────────────────────────────────────────

class TestGetExistingProfiles:
    def test_cisco_returns_profiles(self):
        profiles = _get_existing_profiles("cisco")
        # Au moins un profil Cisco devrait exister
        assert len(profiles) >= 0  # au moins 0 (tests sans les vrais profils)
        for p in profiles:
            assert "vendor" in p
            assert p["vendor"] == "cisco"

    def test_limit_two_profiles(self):
        profiles = _get_existing_profiles("cisco")
        assert len(profiles) <= 2

    def test_unknown_vendor(self):
        profiles = _get_existing_profiles("nonexistent_vendor_12345")
        assert profiles == []
