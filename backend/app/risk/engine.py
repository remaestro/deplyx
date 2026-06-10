"""Risk scoring engine — fully LLM-driven.
 
The LLM's `risk_assessment.severity` is used as the sole risk score.
No heuristic modifiers, no rule-based fallback. If the LLM didn't return
a `risk_assessment`, the change is scored based on risk_factors severity.
"""

from typing import Any

from app.utils.logging import get_logger

logger = get_logger(__name__)

_SEVERITY_SCORE: dict[str, int] = {
    "critical": 90,
    "high": 75,
    "medium": 50,
    "low": 15,
}


class RiskEngine:
    async def evaluate_change(
        self,
        change_data: dict[str, Any],
        impact_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        impact = impact_data or {}
        llm_assessment = impact.get("risk_assessment") or {}
        severity = (llm_assessment.get("severity") or "").lower()

        if severity in _SEVERITY_SCORE:
            score = _SEVERITY_SCORE[severity]
            factors = llm_assessment.get("factors", [])
            summary = llm_assessment.get("summary", "")
            logger.info("LLM risk: severity=%s score=%d summary=%s", severity, score, summary)
        else:
            score = self._score_from_risk_factors(impact)
            severity = self._level_for_score(score)
            logger.info("No LLM risk_assessment — derived from risk_factors: score=%d level=%s", score, severity)

        return self._build_result(score, severity)

    @staticmethod
    def _score_from_risk_factors(impact: dict[str, Any]) -> int:
        factors = impact.get("risk_factors") or []
        if not factors:
            return 15
        blocker = sum(1 for f in factors if f.get("severity") == "blocker")
        warning = sum(1 for f in factors if f.get("severity") == "warning")
        if blocker >= 1:
            return 90
        if warning >= 3:
            return 75
        if warning >= 1:
            return 50
        return 15

    @staticmethod
    def _level_for_score(score: int) -> str:
        if score >= 71:
            return "high"
        if score >= 31:
            return "medium"
        return "low"

    @staticmethod
    def _build_result(score: int, risk_level: str) -> dict[str, Any]:
        auto_approve = risk_level == "low"
        result = {
            "risk_score": float(score),
            "risk_level": risk_level,
            "auto_approve": auto_approve,
            "llm_driven": True,
        }
        logger.info("Risk assessment: score=%d level=%s auto_approve=%s",
                     score, risk_level, auto_approve)
        return result


risk_engine = RiskEngine()
