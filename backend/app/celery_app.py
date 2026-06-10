import asyncio

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery("deplyx", broker=settings.redis_url, backend=settings.redis_url)

celery_app.conf.beat_schedule = {
    "check-approval-timeouts": {
        "task": "app.tasks.check_timeouts",
        "schedule": crontab(minute="*/30"),
    },
    "sync-pull-connectors": {
        "task": "app.tasks.sync_pull_connectors",
        "schedule": crontab(minute="*/5"),
    },
    "poll-dead-letter": {
        "task": "app.tasks.poll_dead_letter",
        "schedule": crontab(minute="*/2"),
    },
    "reconcile-graph-pg": {
        "task": "app.tasks.reconcile_graph_pg",
        "schedule": crontab(minute="*/10"),
    },
}

_loop = None

def run_async(coro):
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop.run_until_complete(coro)
