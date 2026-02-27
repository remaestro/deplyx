from app.celery_app import celery_app, run_async
from app.services import change_service
from app.services.pipeline_services import get_risk_evaluator
from app.tasks.pipeline.base import with_change


@celery_app.task(name="app.tasks.pipeline.score_risk", bind=True, max_retries=3)
def score_risk(self, context: dict):
    trace_id = context["trace_id"]
    change_id = context["change_id"]

    async def _do(db, change):
        evaluator = get_risk_evaluator()
        target_ids = context.get("target_components", [])
        incident_history_count = await change_service.get_incident_history_count(db, target_ids, exclude_change_id=change.id)
        change_data = {
            "environment": change.environment,
            "rollback_plan": change.rollback_plan,
            "maintenance_window_start": change.maintenance_window_start,
            "maintenance_window_end": change.maintenance_window_end,
            "target_components": target_ids,
            "incident_history_count": incident_history_count,
            "action": change.action,
        }
        risk_result = await evaluator.evaluate(change_data, context.get("impact", {}))
        change.risk_score = risk_result["risk_score"]
        change.risk_level = risk_result["risk_level"]
        await db.flush()
        context["risk_result"] = risk_result
        return context

    return run_async(with_change(change_id, trace_id, "scoring_risk", _do))
