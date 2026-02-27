def test_reconcile_graph_pg_task_runs(monkeypatch):
    def _fake_run_async(coro):
        coro.close()
        return {"pg_distinct_nodes": 1, "graph_nodes": 1, "drift_count": 0}

    monkeypatch.setattr(
        "app.tasks.reconcile_graph_pg.run_async",
        _fake_run_async,
    )

    from app.tasks.reconcile_graph_pg import reconcile_graph_pg

    result = reconcile_graph_pg()
    assert result["drift_count"] == 0
