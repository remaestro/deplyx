from app.tasks.pipeline.chain import submit_analysis_chain


class _FakeSig:
    def __init__(self, name: str):
        self.name = name


class _FakeChain:
    def __init__(self, *sigs):
        self.sigs = sigs

    def apply_async(self):
        return {"queued": [s.name for s in self.sigs]}



def test_chain_wiring(monkeypatch):
    calls = []

    def fake_signature(name, kwargs=None):
        calls.append((name, kwargs))
        return _FakeSig(name)

    monkeypatch.setattr("app.tasks.pipeline.chain.celery_app.signature", fake_signature)
    monkeypatch.setattr("app.tasks.pipeline.chain.chain", lambda *args: _FakeChain(*args))

    result = submit_analysis_chain("c1", "t1")

    assert result["queued"][0] == "app.tasks.pipeline.fetch_change_data"
    assert calls[0][1] == {"change_id": "c1", "trace_id": "t1"}
