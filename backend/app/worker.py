import asyncio

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery("deplyx", broker=settings.redis_url, backend=settings.redis_url)

celery_app.conf.beat_schedule = {
    "check-approval-timeouts": {
        "task": "app.tasks.check_timeouts",
        "schedule": crontab(minute="*/30"),  # Every 30 minutes
    },
    "sync-pull-connectors": {
        "task": "app.tasks.sync_pull_connectors",
        "schedule": crontab(minute="*/5"),  # Every 5 minutes
    },
}


def _run_async(coro):
    """Helper to run async code inside sync Celery tasks."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.tasks.health")
def health_task() -> str:
    return "worker-ok"


@celery_app.task(name="app.tasks.analyze_change")
def task_analyze_change(change_id: str) -> dict:
    """Run impact analysis + risk scoring + workflow routing for a change."""

    async def _do():
        from app.core.database import AsyncSessionLocal
        from app.risk.engine import risk_engine
        from app.services import change_service, impact_service
        from app.workflow.engine import workflow_engine

        async with AsyncSessionLocal() as db:
            change = await change_service.get_change(db, change_id)
            if change is None:
                return {"error": "Change not found"}

            # Impact analysis
            target_ids = [ic.graph_node_id for ic in change.impacted_components if ic.impact_level == "direct"]
            impact = await impact_service.analyze_impact(target_ids)
            incident_history_count = await change_service.get_incident_history_count(
                db,
                target_ids,
                exclude_change_id=change.id,
            )

            # Risk scoring
            change_data = {
                "environment": change.environment,
                "rollback_plan": change.rollback_plan,
                "maintenance_window_start": change.maintenance_window_start,
                "maintenance_window_end": change.maintenance_window_end,
                "target_components": target_ids,
                "incident_history_count": incident_history_count,
            }
            risk_result = await risk_engine.evaluate_change(change_data, impact)

            # Update change
            change.risk_score = risk_result["risk_score"]
            change.risk_level = risk_result["risk_level"]

            # Route through workflow
            routing = await workflow_engine.route_change(db, change, risk_result, change.created_by)

            await db.commit()

            return {
                "change_id": change_id,
                "risk_score": risk_result["risk_score"],
                "risk_level": risk_result["risk_level"],
                "workflow": routing,
            }

    return _run_async(_do())


@celery_app.task(name="app.tasks.check_timeouts")
def task_check_timeouts() -> dict:
    """Check all pending approvals for timeouts."""

    async def _do():
        from sqlalchemy import select

        from app.core.database import AsyncSessionLocal
        from app.models.approval import Approval
        from app.workflow.engine import workflow_engine

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Approval.change_id).where(Approval.status == "Pending").distinct())
            change_ids = [row[0] for row in result.all()]

            total_timed_out = 0
            for cid in change_ids:
                count = await workflow_engine.handle_timeout(db, cid)
                total_timed_out += count

            await db.commit()
            return {"checked_changes": len(change_ids), "timed_out_approvals": total_timed_out}

    return _run_async(_do())


@celery_app.task(name="app.tasks.sync_pull_connectors")
def task_sync_pull_connectors() -> dict:
    """Sync connectors configured in pull mode that are due based on interval."""

    async def _do():
        from app.core.database import AsyncSessionLocal
        from app.services import connector_service

        async with AsyncSessionLocal() as db:
            result = await connector_service.sync_due_pull_connectors(db)
            await db.commit()
            return result

    return _run_async(_do())
