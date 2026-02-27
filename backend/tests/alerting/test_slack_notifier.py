import pytest

from app.alerting.slack_notifier import SlackNotifier


class _Resp:
    def __init__(self, status_code: int):
        self.status_code = status_code


class _Client:
    def __init__(self, status_code: int):
        self.status_code = status_code

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *_args, **_kwargs):
        return _Resp(self.status_code)


@pytest.mark.asyncio
async def test_slack_notifier_success(monkeypatch):
    monkeypatch.setattr("app.alerting.slack_notifier.httpx.AsyncClient", lambda timeout: _Client(200))
    notifier = SlackNotifier("https://example.test/webhook")
    assert await notifier.send("title", "body") is True


@pytest.mark.asyncio
async def test_slack_notifier_failure(monkeypatch):
    monkeypatch.setattr("app.alerting.slack_notifier.httpx.AsyncClient", lambda timeout: _Client(500))
    notifier = SlackNotifier("https://example.test/webhook")
    assert await notifier.send("title", "body") is False
