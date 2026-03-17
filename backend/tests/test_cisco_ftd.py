import pytest

from app.connectors import cisco_ftd


@pytest.mark.asyncio
async def test_cisco_ftd_sync_collects_inventory_rules_and_vpn_via_ssh(monkeypatch: pytest.MonkeyPatch):
    merged_nodes: list[tuple[str, str, dict]] = []
    relationships: list[tuple[str, str, str, str, str]] = []

    async def _merge_node(label, node_id, props):
        merged_nodes.append((label, node_id, props))
        return {"id": node_id}

    async def _create_relationship(src_label, src_id, rel_type, dst_label, dst_id):
        relationships.append((src_label, src_id, rel_type, dst_label, dst_id))
        return {}

    outputs = {
        "show version": """
Cisco Firepower Threat Defense for FTD1-2
Version 7.0.1
Serial Number: FPR1234567
Model : Firepower 2110
""",
        "show interface ip brief": """
Interface                IP-Address      OK? Method Status                Protocol
GigabitEthernet0/0       192.168.170.10  YES manual up                    up
GigabitEthernet0/1       unassigned      YES unset  administratively down down
""",
        "show route": """
C    192.168.170.0 255.255.255.0 is directly connected, GigabitEthernet0/0
S    10.10.0.0 255.255.0.0 [1/0] via 192.168.170.1, GigabitEthernet0/0
""",
        "show access-list": """
access-list OUTSIDE-IN line 1 extended permit tcp any host 10.10.10.20 eq https
access-list OUTSIDE-IN line 2 extended deny ip any 10.20.0.0 255.255.0.0
""",
        "show vpn-sessiondb detail l2l": """
Connection : BRANCH-A
Peer IP Address: 203.0.113.10
""",
    }

    def _run_ssh(self, command: str) -> str:
        return outputs[command]

    monkeypatch.setattr(cisco_ftd.neo4j_client, "merge_node", _merge_node)
    monkeypatch.setattr(cisco_ftd.neo4j_client, "create_relationship", _create_relationship)
    monkeypatch.setattr(cisco_ftd.CiscoFTDConnector, "_run_ssh", _run_ssh)

    connector = cisco_ftd.CiscoFTDConnector({
        "host": "192.168.170.10",
        "username": "iptadmin",
        "password": "secret",
        "transport": "ssh",
    })
    result = await connector.sync()

    assert result["status"] == "synced"
    assert result["synced"]["devices"] == 1
    assert result["synced"]["interfaces"] == 2
    assert result["synced"]["routes"] == 2
    assert result["synced"]["rules"] == 2
    assert result["synced"]["vpn_tunnels"] == 1

    assert any(label == "Device" and node_id == "FTD-FPR1234567" for label, node_id, _props in merged_nodes)
    assert any(label == "Rule" and node_id.startswith("FTD-RULE-") for label, node_id, _props in merged_nodes)
    assert any(label == "VPNTunnel" and node_id.startswith("VPN-TUNNEL-FTD-") for label, node_id, _props in merged_nodes)
    assert any(rel_type == "HAS_RULE" for _src_label, _src_id, rel_type, _dst_label, _dst_id in relationships)
    assert any(rel_type == "HAS_VPN_TUNNEL" for _src_label, _src_id, rel_type, _dst_label, _dst_id in relationships)


@pytest.mark.asyncio
async def test_cisco_ftd_sync_uses_fdm_api_token(monkeypatch: pytest.MonkeyPatch):
    merged_nodes: list[tuple[str, str, dict]] = []

    async def _merge_node(label, node_id, props):
        merged_nodes.append((label, node_id, props))
        return {"id": node_id}

    async def _create_relationship(*_args, **_kwargs):
        return {}

    class _Resp:
        def __init__(self, data, status_code=200):
            self._data = data
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise cisco_ftd.requests.HTTPError(f"status={self.status_code}")

        def json(self):
            return self._data

    def _fake_post(url, **_kwargs):
        if url.endswith("/fdm/token"):
            return _Resp({"access_token": "token-123"})
        raise AssertionError(url)

    def _fake_get(url, **_kwargs):
        if url.endswith("/devices/default/deviceversion"):
            return _Resp({"hostname": "ftd1-2", "serialNumber": "FPRAPI123", "model": "Firepower 2110", "version": "7.0.1"})
        if url.endswith("/devices/default/interfaces/physicalinterfaces?limit=200"):
            return _Resp({"items": [{"name": "GigabitEthernet0/0", "enabled": True, "ipAddress": {"value": "192.168.170.10"}}]})
        if url.endswith("/devices/default/routing/ipv4staticroutes?limit=200"):
            return _Resp({"items": [{"ipAddress": "10.10.0.0", "netMask": "255.255.0.0"}]})
        if url.endswith("/policy/accesspolicies/default/accessrules?limit=200"):
            return _Resp({"items": [{"name": "Allow-HTTPS", "action": "ALLOW", "destinationNetworks": "10.10.10.20", "destinationPorts": "https"}]})
        if url.endswith("/devices/default/vpn/s2svpntunnels?limit=200"):
            return _Resp({"items": [{"name": "BRANCH-A", "peerAddress": "203.0.113.10"}]})
        return _Resp({}, status_code=404)

    monkeypatch.setattr(cisco_ftd.neo4j_client, "merge_node", _merge_node)
    monkeypatch.setattr(cisco_ftd.neo4j_client, "create_relationship", _create_relationship)
    monkeypatch.setattr(cisco_ftd.requests, "post", _fake_post)
    monkeypatch.setattr(cisco_ftd.requests, "get", _fake_get)

    connector = cisco_ftd.CiscoFTDConnector({
        "host": "192.168.170.10",
        "username": "admin",
        "password": "Admin@123",
        "transport": "api",
    })
    result = await connector.sync()

    assert result["status"] == "synced"
    assert result["synced"]["devices"] == 1
    assert result["synced"]["interfaces"] == 1
    assert result["synced"]["routes"] == 1
    assert result["synced"]["rules"] == 1
    assert result["synced"]["vpn_tunnels"] == 1
    assert any(label == "Device" and node_id == "FTD-FPRAPI123" for label, node_id, _props in merged_nodes)