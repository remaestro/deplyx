from app.celery_app import celery_app, run_async
from app.tasks.pipeline.base import with_change


@celery_app.task(name="app.tasks.pipeline.finalise_analysis", bind=True, max_retries=3)
def finalise_analysis(self, context: dict):
    trace_id = context["trace_id"]
    change_id = context["change_id"]

    async def _do(db, change):
        change.analysis_last_error = None
        return {
            "change_id": change.id,
            "trace_id": trace_id,
            "risk_score": change.risk_score,
            "risk_level": change.risk_level,
            "routing": context.get("routing", {}),
        }

    return run_async(with_change(change_id, trace_id, "finalised", _do))
