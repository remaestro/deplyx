from app.celery_app import celery_app, run_async
from app.services.pipeline_services import get_impact_analyzer
from app.tasks.pipeline.base import with_change


@celery_app.task(name="app.tasks.pipeline.compute_impact", bind=True, max_retries=3)
def compute_impact(self, context: dict):
    trace_id = context["trace_id"]
    change_id = context["change_id"]

    async def _do(db, change):
        analyzer = get_impact_analyzer()
        impact = await analyzer.analyze(
            target_node_ids=context.get("target_components", []),
            action=context.get("action"),
            change_type=context.get("change_type"),
            environment=context.get("environment"),
            title=context.get("title"),
        )
        change.impact_cache = impact
        await db.flush()
        context["impact"] = impact
        return context

    return run_async(with_change(change_id, trace_id, "computing_impact", _do))
