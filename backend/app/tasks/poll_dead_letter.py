import json
from datetime import UTC, datetime

from sqlalchemy import select

from app.celery_app import celery_app, run_async
from app.models.change import Change
from app.services.pipeline_services import get_notification_sender
from app.utils.logging import get_logger

logger = get_logger(__name__)

DEAD_LETTER_KEY = "deplyx:dead_letter_queue"
MAX_ATTEMPTS = 3


def _get_redis():
    """Return a synchronous Redis client from the Celery broker URL."""
    import redis
    from app.core.config import settings

    return redis.from_url(settings.CELERY_BROKER_URL, decode_responses=True)


@celery_app.task(name="app.tasks.poll_dead_letter")
def poll_dead_letter() -> dict:
    """Drain the dead-letter queue (Redis list) and send alerts.

    Each item is a JSON object with at least ``change_id``.  Items that cannot
    be processed are pushed back to the queue via RPUSH so they are retried on
    the next poll cycle.
    """

    async def _do():
        from app.core.database import AsyncSessionLocal

        r = _get_redis()
        processed = 0
        requeued = 0
        notified = 0
        sender = get_notification_sender()

        while True:
            raw = r.lpop(DEAD_LETTER_KEY)
            if raw is None:
                break
            try:
                item = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                logger.warning("dead-letter: invalid JSON, discarding: %s", raw[:200])
                continue

            change_id = item.get("change_id")
            attempts = item.get("attempts", 0)

            if attempts >= MAX_ATTEMPTS:
                logger.error("dead-letter: change %s exceeded %d attempts, discarding", change_id, MAX_ATTEMPTS)
                processed += 1
                continue

            try:
                sent = await sender.send(
                    title="Analysis dead-letter detected",
                    body=f"Change {change_id} failed (attempt {attempts + 1})",
                    metadata=item,
                )
                if sent:
                    notified += 1
                processed += 1
            except Exception:
                # Re-queue with incremented attempt counter
                item["attempts"] = attempts + 1
                item["requeued_at"] = datetime.now(UTC).isoformat()
                r.rpush(DEAD_LETTER_KEY, json.dumps(item))
                requeued += 1

        # Fallback: also scan PG for any stuck changes not yet in the queue
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Change).where(
                    Change.analysis_stage == "failed",
                    Change.analysis_attempts >= 3,
                )
            )
            failed = list(result.scalars().all())
            for change in failed:
                sent = await sender.send(
                    title="Analysis dead-letter detected",
                    body=f"Change {change.id} failed after retries",
                    metadata={
                        "change_id": change.id,
                        "analysis_stage": change.analysis_stage,
                        "analysis_attempts": change.analysis_attempts,
                        "trace_id": change.analysis_trace_id or "",
                    },
                )
                if sent:
                    notified += 1

        return {
            "queue_processed": processed,
            "queue_requeued": requeued,
            "pg_stuck": len(failed),
            "notified": notified,
        }

    return run_async(_do())
