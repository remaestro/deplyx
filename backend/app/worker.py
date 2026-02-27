from app.celery_app import celery_app, run_async
from app.tasks.analyze_change import enqueue_analysis

# Ensure task modules are imported so Celery registers them
from app.tasks import poll_dead_letter as _poll_dead_letter  # noqa: F401
from app.tasks import reconcile_graph_pg as _reconcile_graph_pg  # noqa: F401
from app.tasks.pipeline import compute_impact as _compute_impact  # noqa: F401
from app.tasks.pipeline import fetch_change_data as _fetch_change_data  # noqa: F401
from app.tasks.pipeline import finalise_analysis as _finalise_analysis  # noqa: F401
from app.tasks.pipeline import route_workflow as _route_workflow  # noqa: F401
from app.tasks.pipeline import score_risk as _score_risk  # noqa: F401


@celery_app.task(name="app.tasks.health")
def health_task() -> str:
    return "worker-ok"


@celery_app.task(name="app.tasks.analyze_change")
def task_analyze_change(change_id: str) -> dict:
    enqueue_analysis(change_id)
    return {"change_id": change_id, "queued": True}


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

    return run_async(_do())


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

    return run_async(_do())
