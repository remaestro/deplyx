from celery import chain

from app.celery_app import celery_app
from app.tasks.pipeline.base import ensure_trace_id



def submit_analysis_chain(change_id: str, trace_id: str | None = None):
    pipeline_trace_id = ensure_trace_id(trace_id)
    sig = chain(
        celery_app.signature("app.tasks.pipeline.fetch_change_data", kwargs={"change_id": change_id, "trace_id": pipeline_trace_id}),
        celery_app.signature("app.tasks.pipeline.compute_impact"),
        celery_app.signature("app.tasks.pipeline.score_risk"),
        celery_app.signature("app.tasks.pipeline.route_workflow"),
        celery_app.signature("app.tasks.pipeline.finalise_analysis"),
    )
    return sig.apply_async()
