from typing import Any


class FakeImpactAnalyzer:
    async def analyze(
        self,
        target_node_ids: list[str],
        action: str | None,
        change_type: str | None,
        environment: str | None,
        title: str | None,
    ) -> dict[str, Any]:
        return {"target_node_ids": target_node_ids, "action": action, "llm_powered": False}


class FakeRiskEvaluator:
    async def evaluate(self, change_data: dict[str, Any], impact_data: dict[str, Any]) -> dict[str, Any]:
        return {"risk_score": 12.0, "risk_level": "low", "auto_approve": True}


class FakeWorkflowRouter:
    async def route(self, db, change, risk_result: dict[str, Any], user_id: int | None):
        return {"next_step": "auto-approve", "approvals_created": 0}


class FakeNotificationSender:
    async def send(self, title: str, body: str, metadata: dict[str, Any] | None = None) -> bool:
        return True
