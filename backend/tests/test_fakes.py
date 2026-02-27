"""Unit tests for fake implementations used in testing.

Validates that fakes behave correctly and satisfy the contracts they stand in
for.
"""

import pytest


# ── FakeGraphClient ──────────────────────────────────────────────────────

class TestFakeGraphClient:
    def _make(self):
        from tests.fakes.fake_graph_client import FakeGraphClient
        return FakeGraphClient()

    @pytest.mark.asyncio
    async def test_merge_node(self):
        g = self._make()
        await g.merge_node("Device", "D1", {"hostname": "fw01"})
        assert "D1" in g.nodes
        assert g.nodes["D1"]["hostname"] == "fw01"

    @pytest.mark.asyncio
    async def test_create_relationship(self):
        g = self._make()
        await g.create_relationship("Device", "D1", "HAS_INTERFACE", "Interface", "IF1")
        assert len(g.relationships) == 1
        assert g.relationships[0]["rel_type"] == "HAS_INTERFACE"

    @pytest.mark.asyncio
    async def test_get_full_topology(self):
        g = self._make()
        await g.merge_node("Device", "D1", {})
        topo = await g.get_full_topology()
        assert len(topo["nodes"]) == 1

    @pytest.mark.asyncio
    async def test_close(self):
        g = self._make()
        await g.close()
        assert g._closed is True


# ── FakeChangeRepository ─────────────────────────────────────────────────

class TestFakeChangeRepository:
    def _make(self):
        from tests.fakes.fake_repositories import FakeChangeRepository
        return FakeChangeRepository()

    @pytest.mark.asyncio
    async def test_save_and_get(self):
        repo = self._make()
        saved = await repo.save({"title": "test"})
        assert saved["id"] == 1
        fetched = await repo.get(1)
        assert fetched["title"] == "test"

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self):
        repo = self._make()
        assert await repo.get(999) is None

    @pytest.mark.asyncio
    async def test_list_all(self):
        repo = self._make()
        await repo.save({"title": "a"})
        await repo.save({"title": "b"})
        assert len(await repo.list_all()) == 2


# ── FakePolicyRepository ─────────────────────────────────────────────────

class TestFakePolicyRepository:
    @pytest.mark.asyncio
    async def test_get_active(self):
        from tests.fakes.fake_repositories import FakePolicyRepository

        repo = FakePolicyRepository([{"name": "wf", "is_active": True, "value": 42}])
        found = await repo.get_active("wf")
        assert found is not None
        assert found["value"] == 42

    @pytest.mark.asyncio
    async def test_get_active_missing(self):
        from tests.fakes.fake_repositories import FakePolicyRepository

        repo = FakePolicyRepository([])
        assert await repo.get_active("nope") is None


# ── FakeApprovalRepository ───────────────────────────────────────────────

class TestFakeApprovalRepository:
    @pytest.mark.asyncio
    async def test_create_and_list(self):
        from tests.fakes.fake_repositories import FakeApprovalRepository

        repo = FakeApprovalRepository()
        await repo.create({"change_id": 1, "approver": "admin"})
        result = await repo.list_for_change(1)
        assert len(result) == 1
        assert result[0]["approver"] == "admin"

    @pytest.mark.asyncio
    async def test_filter_by_change_id(self):
        from tests.fakes.fake_repositories import FakeApprovalRepository

        repo = FakeApprovalRepository()
        await repo.create({"change_id": 1})
        await repo.create({"change_id": 2})
        assert len(await repo.list_for_change(1)) == 1
        assert len(await repo.list_for_change(2)) == 1


# ── FakeAuditRepository ─────────────────────────────────────────────────

class TestFakeAuditRepository:
    @pytest.mark.asyncio
    async def test_log_and_list(self):
        from tests.fakes.fake_repositories import FakeAuditRepository

        repo = FakeAuditRepository()
        await repo.log({"action": "approve", "user": "admin"})
        entries = await repo.list_all()
        assert len(entries) == 1
        assert entries[0]["action"] == "approve"
        assert "timestamp" in entries[0]


# ── FakeAlertNotifier ────────────────────────────────────────────────────

class TestFakeAlertNotifier:
    @pytest.mark.asyncio
    async def test_send_records_call(self):
        from tests.fakes.fake_alert_notifier import FakeAlertNotifier

        n = FakeAlertNotifier()
        ok = await n.send("title", "body", {"k": "v"})
        assert ok is True
        assert len(n.send_calls) == 1
        assert n.send_calls[0]["title"] == "title"

    def test_record_stores_event(self):
        from tests.fakes.fake_alert_notifier import FakeAlertNotifier
        from app.alerting.notifier import AlertEvent

        n = FakeAlertNotifier()
        evt = AlertEvent(event_type="test", change_id=1, attempts=0, last_error="")
        n.record(evt)
        assert len(n.events) == 1
