def test_poll_dead_letter_task_runs(monkeypatch):
    def _fake_run_async(coro):
        coro.close()
        return {"failed_changes": 0, "notified": 0}

    monkeypatch.setattr(
        "app.tasks.poll_dead_letter.run_async",
        _fake_run_async,
    )

    from app.tasks.poll_dead_letter import poll_dead_letter

    result = poll_dead_letter()
    assert result["failed_changes"] == 0
