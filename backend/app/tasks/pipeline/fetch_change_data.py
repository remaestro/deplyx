from app.celery_app import celery_app, run_async
from app.tasks.pipeline.base import ensure_trace_id, with_change


@celery_app.task(name="app.tasks.pipeline.fetch_change_data", bind=True, max_retries=3)
def fetch_change_data(self, change_id: str, trace_id: str | None = None):
    trace = ensure_trace_id(trace_id)

    async def _do(db, change):
        target_ids = [ic.graph_node_id for ic in change.impacted_components if ic.impact_level == "direct"]
        return {
            "change_id": change.id,
            "trace_id": trace,
            "created_by": change.created_by,
            "action": change.action,
            "change_type": change.change_type,
            "environment": change.environment,
            "title": change.title,
            "rollback_plan": change.rollback_plan,
            "maintenance_window_start": change.maintenance_window_start,
            "maintenance_window_end": change.maintenance_window_end,
            "target_components": target_ids,
        }

    return run_async(with_change(change_id, trace, "fetching_data", _do))
