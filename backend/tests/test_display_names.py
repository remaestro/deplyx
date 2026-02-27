"""Unit tests for app.connectors.display_name builders."""

import pytest

from app.connectors import display_name as dn


class TestDeviceBuilder:
    def test_basic_format(self):
        result = dn.device(dn.VENDOR_FORTINET, dn.FUNCTION_FIREWALL, "fw01")
        assert "Fortinet" in result or "fortinet" in result.lower()
        assert "fw01" in result
        assert "\u2014" in result  # em-dash

    @pytest.mark.parametrize(
        "vendor,function_",
        [
            (dn.VENDOR_PALO_ALTO, dn.FUNCTION_FIREWALL),
            (dn.VENDOR_CISCO, dn.FUNCTION_SWITCH),
            (dn.VENDOR_JUNIPER, dn.FUNCTION_ROUTER),
            (dn.VENDOR_ARUBA, dn.FUNCTION_SWITCH),
            (dn.VENDOR_VYOS, dn.FUNCTION_ROUTER),
            (dn.VENDOR_STRONGSWAN, dn.FUNCTION_VPN),
            (dn.VENDOR_SNORT, dn.FUNCTION_IDS),
            (dn.VENDOR_OPENLDAP, dn.FUNCTION_DIRECTORY),
            (dn.VENDOR_NGINX, dn.FUNCTION_PROXY),
            (dn.VENDOR_POSTGRES, dn.FUNCTION_DATABASE),
            (dn.VENDOR_REDIS, dn.FUNCTION_CACHE),
            (dn.VENDOR_ELASTICSEARCH, dn.FUNCTION_SEARCH),
            (dn.VENDOR_GRAFANA, dn.FUNCTION_MONITORING),
            (dn.VENDOR_PROMETHEUS, dn.FUNCTION_METRICS),
        ],
    )
    def test_all_vendor_function_combos(self, vendor, function_):
        result = dn.device(vendor, function_, "host1")
        assert isinstance(result, str)
        assert len(result) > 0
        assert "host1" in result


class TestInterfaceBuilder:
    def test_contains_ifname(self):
        parent = dn.device(dn.VENDOR_CISCO, dn.FUNCTION_SWITCH, "sw01")
        result = dn.interface("eth0", parent)
        assert "eth0" in result

    def test_contains_parent(self):
        parent = dn.device(dn.VENDOR_CISCO, dn.FUNCTION_SWITCH, "sw01")
        result = dn.interface("eth0", parent)
        assert parent in result


class TestRuleBuilder:
    def test_contains_rule_id_and_parent(self):
        parent = dn.device(dn.VENDOR_FORTINET, dn.FUNCTION_FIREWALL, "fw01")
        result = dn.rule("policy-100", parent)
        assert "policy-100" in result
        assert parent in result

    def test_empty_rule_id(self):
        parent = dn.device(dn.VENDOR_PALO_ALTO, dn.FUNCTION_FIREWALL, "pa01")
        result = dn.rule("", parent)
        assert isinstance(result, str)


class TestIPAddressBuilder:
    def test_basic(self):
        result = dn.ip_address("192.168.1.1")
        assert "192.168.1.1" in result

    def test_ipv6(self):
        result = dn.ip_address("::1")
        assert "::1" in result


class TestApplicationBuilder:
    def test_replaces_hyphens(self):
        result = dn.application("my-cool-app")
        assert "-" not in result

    def test_replaces_underscores(self):
        result = dn.application("my_cool_app")
        assert "_" not in result

    def test_plain_name(self):
        result = dn.application("nginx")
        assert "nginx" in result.lower()
