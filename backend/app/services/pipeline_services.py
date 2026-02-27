from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.interfaces import ImpactAnalyzer, NotificationSender, RiskEvaluator, WorkflowRouter
from app.models.change import Change
from app.risk.engine import risk_engine
from app.services import impact_service
from app.workflow.engine import workflow_engine
from app.alerting.notifier import get_notifier


class DefaultImpactAnalyzer(ImpactAnalyzer):
    async def analyze(
        self,
        target_node_ids: list[str],
        action: str | None,
        change_type: str | None,
        environment: str | None,
        title: str | None,
    ) -> dict[str, Any]:
        return await impact_service.analyze_impact(
            target_node_ids,
            action=action,
            change_type=change_type,
            environment=environment,
            title=title,
        )


class DefaultRiskEvaluator(RiskEvaluator):
    async def evaluate(self, change_data: dict[str, Any], impact_data: dict[str, Any]) -> dict[str, Any]:
        return await risk_engine.evaluate_change(change_data, impact_data)


class DefaultWorkflowRouter(WorkflowRouter):
    async def route(
        self,
        db: AsyncSession,
        change: Change,
        risk_result: dict[str, Any],
        user_id: int | None,
    ) -> dict[str, Any]:
        return await workflow_engine.route_change(db, change, risk_result, user_id)


class DefaultNotificationSender(NotificationSender):
    async def send(self, title: str, body: str, metadata: dict[str, Any] | None = None) -> bool:
        notifier = get_notifier()
        return await notifier.send(title=title, body=body, metadata=metadata)



def get_impact_analyzer() -> ImpactAnalyzer:
    return DefaultImpactAnalyzer()



def get_risk_evaluator() -> RiskEvaluator:
    return DefaultRiskEvaluator()



def get_workflow_router() -> WorkflowRouter:
    return DefaultWorkflowRouter()



def get_notification_sender() -> NotificationSender:
    return DefaultNotificationSender()
