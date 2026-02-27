import pytest

from app.models.change import Change


@pytest.mark.asyncio
async def test_change_stage_defaults(db):
    change = Change(
        title="t",
        change_type="Firewall",
        environment="Prod",
        description="d",
        execution_plan="e",
        rollback_plan="r",
        created_by=1,
    )
    db.add(change)
    await db.flush()

    assert change.analysis_stage == "pending"
    assert change.analysis_attempts == 0
    assert change.analysis_last_error is None
    assert change.analysis_trace_id is None
