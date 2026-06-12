"""Tests pour le module fingerprint (reconnaissance profile-driven)."""

from __future__ import annotations

import pytest

from app.connectors_v2.fingerprint import (
    fingerprint_from_banner,
    fingerprint_from_cmd_output,
    enrich_profile_match_patterns,
    _legacy_fingerprint_from_banner,
    _legacy_fingerprint_from_cmd_output,
)
from app.connectors_v2.device_profile import DeviceProfile, fingerprint_device


# ── Legacy fallback (devrait matcher les banners connues) ──────────

class TestLegacyBanner:
    def test_cisco_ios(self):
        r = _legacy_fingerprint_from_banner("Cisco IOS Software, C3850 Software")
        assert r["vendor"] == "cisco"
        assert r["os"] == "ios"

    def test_cisco_ftd(self):
        r = _legacy_fingerprint_from_banner("Cisco Firepower FTD")
        assert r["vendor"] == "cisco"
        assert r["os"] == "ftd"

    def test_cisco_nxos(self):
        r = _legacy_fingerprint_from_banner("Cisco NX-OS Software")
        assert r["vendor"] == "cisco"
        assert r["os"] == "nxos"

    def test_juniper(self):
        r = _legacy_fingerprint_from_banner("Juniper Junos")
        assert r["vendor"] == "juniper"
        assert r["os"] == "junos"

    def test_fortinet(self):
        r = _legacy_fingerprint_from_banner("FortiGate-100D")
        assert r["vendor"] == "fortinet"
        assert r["os"] == "fortios"

    def test_paloalto(self):
        r = _legacy_fingerprint_from_banner("Palo Alto Networks PAN-OS")
        assert r["vendor"] == "paloalto"
        assert r["os"] == "panos"

    def test_vyos(self):
        r = _legacy_fingerprint_from_banner("VyOS 1.3")
        assert r["vendor"] == "vyos"
        assert r["os"] == "vyos"

    def test_aruba(self):
        r = _legacy_fingerprint_from_banner("Aruba Networks")
        assert r["vendor"] == "aruba"
        assert r["os"] == "aruba"

    def test_checkpoint(self):
        r = _legacy_fingerprint_from_banner("Check Point")
        assert r["vendor"] == "checkpoint"
        assert r["os"] == "checkpoint"

    def test_linux(self):
        r = _legacy_fingerprint_from_banner("Linux ubuntu")
        assert r["vendor"] == "linux"

    def test_generic_ssh(self):
        r = _legacy_fingerprint_from_banner("SSH-2.0-OpenSSH")
        assert r["vendor"] == "generic"

    def test_unknown(self):
        r = _legacy_fingerprint_from_banner("Totally unknown device")
        assert r["vendor"] is None


# ── Legacy cmd output ──────────────────────────────────────────────

class TestLegacyCmdOutput:
    def test_cisco_show_version(self):
        r = _legacy_fingerprint_from_cmd_output(
            "Cisco IOS Software, Version 16.12.3\nswitch1 uptime is 2 weeks\n"
            "Processor board ID FOC1234ABCD"
        )
        assert r["vendor"] == "cisco"
        assert r["os"] == "ios"
        assert r["os_version"] == "16.12.3"
        assert r["hostname"] == "switch1"
        assert r["model"] == "FOC1234ABCD"

    def test_junos(self):
        r = _legacy_fingerprint_from_cmd_output("Junos: 20.4R3")
        assert r["vendor"] == "juniper"
        assert r["os"] == "junos"

    def test_empty(self):
        r = _legacy_fingerprint_from_cmd_output("")
        assert r["vendor"] is None


# ── Profile-driven banner matching ─────────────────────────────────

class TestProfileDrivenBanner:
    def test_with_profiles_matches_cisco(self):
        profiles = DeviceProfile.load_all()
        r = fingerprint_from_banner("Cisco IOS Software", profiles)
        assert r["vendor"] == "cisco"

    def test_with_profiles_matches_fortinet(self):
        profiles = DeviceProfile.load_all()
        r = fingerprint_from_banner("FortiGate-100D", profiles)
        assert r["vendor"] == "fortinet"

    def test_with_profiles_no_match_fallsback(self):
        profiles = DeviceProfile.load_all()
        r = fingerprint_from_banner("Totally unknown device", profiles)
        assert r["vendor"] is None

    def test_without_profiles_uses_legacy(self):
        r = fingerprint_from_banner("Cisco IOS", profiles=None)
        assert r["vendor"] == "cisco"


# ── Profile-driven cmd output matching ─────────────────────────────

class TestProfileDrivenCmdOutput:
    def test_with_profiles_matches_cisco(self):
        profiles = DeviceProfile.load_all()
        r = fingerprint_from_cmd_output("Cisco IOS Software, Version 16.12", profiles)
        assert r["vendor"] == "cisco"

    def test_with_profiles_matches_fortinet(self):
        profiles = DeviceProfile.load_all()
        r = fingerprint_from_cmd_output("FortiGate-60F", profiles)
        assert r["vendor"] == "fortinet"

    def test_without_profiles_uses_legacy(self):
        r = fingerprint_from_cmd_output("Cisco IOS", profiles=None)
        assert r["vendor"] == "cisco"


# ── enrich_profile_match_patterns ─────────────────────────────────

class TestEnrichProfile:
    def test_already_has_patterns_unchanged(self):
        """Un profil qui a déjà des patterns ne doit pas être modifié."""
        data = {
            "name": "test-profile",
            "vendor": "cisco",
            "os": "ios",
            "match_banner": ["Cisco"],
            "match_cmd_output": ["cisco"],
            "transports": [{"type": "ssh", "priority": 10, "device_type": "cisco_ios"}],
            "commands": {"show_version": "show version"},
            "command_groups": {"system": {"refs": ["show_version"]}},
        }
        profile = DeviceProfile(data)
        enriched = enrich_profile_match_patterns(profile, {})
        assert enriched.match_banner == ["Cisco"]
        assert enriched.match_cmd_output == ["cisco"]

    def test_empty_gets_enriched_for_cisco(self):
        data = {
            "name": "test-cisco",
            "vendor": "cisco",
            "os": "ios",
            "match_banner": [],
            "match_cmd_output": [],
            "transports": [],
            "commands": {},
            "command_groups": {},
        }
        profile = DeviceProfile(data)
        enriched = enrich_profile_match_patterns(profile, {})
        assert enriched.match_banner == ["Cisco", "IOS"]
        assert enriched.match_cmd_output == ["cisco", "ios", "Cisco IOS Software"]

    def test_empty_gets_enriched_for_fortinet(self):
        data = {
            "name": "test-fortinet",
            "vendor": "fortinet",
            "os": "fortios",
            "match_banner": [],
            "match_cmd_output": [],
            "transports": [],
            "commands": {},
            "command_groups": {},
        }
        profile = DeviceProfile(data)
        enriched = enrich_profile_match_patterns(profile, {})
        assert "Fortinet" in enriched.match_banner
        assert "FortiGate" in enriched.match_banner

    def test_unknown_vendor_unchanged(self):
        data = {
            "name": "test-unknown",
            "vendor": "unknown_vendor",
            "os": "unknown_os",
            "match_banner": [],
            "match_cmd_output": [],
            "transports": [],
            "commands": {},
            "command_groups": {},
        }
        profile = DeviceProfile(data)
        enriched = enrich_profile_match_patterns(profile, {})
        assert enriched.match_banner == []
        assert enriched.match_cmd_output == []
