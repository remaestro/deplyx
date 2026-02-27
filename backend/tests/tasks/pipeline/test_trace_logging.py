import json
import logging

from app.tasks.pipeline.logging_utils import log_pipeline_event


def test_trace_logging_json_payload(caplog):
    caplog.set_level(logging.INFO)
    log_pipeline_event("stage_ok", "trace-1", "change-1", stage="fetching_data")

    message = caplog.records[-1].message
    payload = json.loads(message)
    assert payload["trace_id"] == "trace-1"
    assert payload["change_id"] == "change-1"
    assert payload["stage"] == "fetching_data"
