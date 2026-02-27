import pytest

from app.connectors import fortinet


class _Resp:
    def __init__(self, data, ok=True):
        self._data = data
        self.ok = ok

    def json(self):
        return self._data


@pytest.mark.asyncio
async def test_fortinet_sync_sets_display_name(monkeypatch: pytest.MonkeyPatch):
    calls = []

    async def _merge_node(label, node_id, props):
        calls.append((label, node_id, props))
        return {"id": node_id}

    async def _create_relationship(*_args, **_kwargs):
        return {}

    def _fake_get(url, **_kwargs):
        if url.endswith('/monitor/system/status'):
            return _Resp({"results": {"hostname": "fw-dc1-01", "serial": "FGT001"}})
        if url.endswith('/cmdb/system/interface'):
            return _Resp({"results": [{"name": "port1", "status": "up", "speed": "1000"}]})
        if url.endswith('/cmdb/firewall/policy'):
            return _Resp({"results": [{"policyid": 1, "name": "allow-web", "srcaddr": [{"name": "all"}], "dstaddr": [{"name": "web"}], "action": "accept"}]})
        return _Resp({}, ok=False)

    monkeypatch.setattr(fortinet.neo4j_client, "merge_node", _merge_node)
    monkeypatch.setattr(fortinet.neo4j_client, "create_relationship", _create_relationship)
    monkeypatch.setattr(fortinet.requests, "get", _fake_get)

    connector = fortinet.FortinetConnector({"host": "127.0.0.1", "api_token": "x", "verify_ssl": False})
    result = await connector.sync()

    assert result["status"] == "synced"
    assert any(label == "Device" and "display_name" in props for label, _id, props in calls)
    assert any(label == "Interface" and "display_name" in props for label, _id, props in calls)
    assert any(label == "Rule" and "display_name" in props for label, _id, props in calls)
