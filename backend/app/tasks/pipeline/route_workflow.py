from app.celery_app import celery_app, run_async
from app.services.pipeline_services import get_workflow_router
from app.tasks.pipeline.base import with_change


@celery_app.task(name="app.tasks.pipeline.route_workflow", bind=True, max_retries=3)
def route_workflow(self, context: dict):
    trace_id = context["trace_id"]
    change_id = context["change_id"]

    async def _do(db, change):
        router = get_workflow_router()
        routing = await router.route(db, change, context.get("risk_result", {}), context.get("created_by"))
        context["routing"] = routing
        return context

    return run_async(with_change(change_id, trace_id, "routing_workflow", _do))
