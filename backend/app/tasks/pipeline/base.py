import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.database import AsyncSessionLocal
from app.models.change import Change
from app.services import change_service
from app.tasks.pipeline.errors import ChangeNotFoundError
from app.tasks.pipeline.logging_utils import log_pipeline_event


async def with_change(
    change_id: str,
    trace_id: str,
    stage: str,
    fn: Callable[[Any, Change], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        change = await change_service.get_change(db, change_id)
        if change is None:
            raise ChangeNotFoundError(change_id)

        await change_service.set_analysis_stage(db, change_id, stage, trace_id=trace_id)

        try:
            result = await fn(db, change)
            await change_service.set_analysis_last_error(db, change_id, None)
            await db.commit()
            log_pipeline_event("stage_ok", trace_id, change_id, stage=stage)
            return result
        except Exception as exc:
            await change_service.increment_analysis_attempts(db, change_id)
            await change_service.set_analysis_stage(db, change_id, "failed", error=str(exc), trace_id=trace_id)
            await db.commit()
            log_pipeline_event("stage_error", trace_id, change_id, stage=stage, error=str(exc))
            raise



def ensure_trace_id(trace_id: str | None) -> str:
    return trace_id or str(uuid.uuid4())
