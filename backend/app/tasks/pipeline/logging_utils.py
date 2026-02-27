import json
from typing import Any

from app.utils.logging import get_logger

logger = get_logger(__name__)



def log_pipeline_event(event: str, trace_id: str, change_id: str, **fields: Any) -> None:
    payload = {
        "event": event,
        "trace_id": trace_id,
        "change_id": change_id,
        **fields,
    }
    logger.info("%s", json.dumps(payload, default=str))
