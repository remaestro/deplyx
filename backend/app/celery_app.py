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



def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
