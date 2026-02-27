import pytest

from app.services.pipeline_services import (
    get_impact_analyzer,
    get_notification_sender,
    get_risk_evaluator,
    get_workflow_router,
)
from tests.fakes import (
    FakeImpactAnalyzer,
    FakeNotificationSender,
    FakeRiskEvaluator,
    FakeWorkflowRouter,
)


def test_default_factories_return_adapters():
    assert get_impact_analyzer() is not None
    assert get_risk_evaluator() is not None
    assert get_workflow_router() is not None
    assert get_notification_sender() is not None


@pytest.mark.asyncio
async def test_fake_adapters_are_usable():
    impact = await FakeImpactAnalyzer().analyze(["A"], "add_rule", "Firewall", "Prod", "t")
    risk = await FakeRiskEvaluator().evaluate({}, {})
    routing = await FakeWorkflowRouter().route(None, None, {}, None)
    sent = await FakeNotificationSender().send("title", "body")

    assert impact["target_node_ids"] == ["A"]
    assert risk["risk_level"] == "low"
    assert routing["next_step"] == "auto-approve"
    assert sent is True
