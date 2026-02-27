from app.tasks.pipeline.chain import submit_analysis_chain



def enqueue_analysis(change_id: str, trace_id: str | None = None):
    return submit_analysis_chain(change_id=change_id, trace_id=trace_id)
