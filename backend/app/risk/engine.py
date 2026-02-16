"""Risk scoring engine — LLM-driven with rule-based modifiers.

When an LLM risk assessment is available, its severity sets the **base score**:
  critical → 80,  high → 60,  medium → 40,  low → 20

Rule-based modifiers then adjust up or down (capped at 0–100):
  + Production environment       +8
  + Core / critical device       +10
  + > 10 dependencies            +5
  + No rollback plan             +7
  + Outside maintenance window   +8
  + Incident history             +5
  + Action inherent severity     +2 … +10

When no LLM assessment is available, the engine falls back to pure rule-based
scoring (same factors, higher weights, out of 215 raw max).

Score → level mapping:
  0–30  → low   (auto-approve)
  31–70 → medium (targeted approval)
  71+   → high  (CAB required)
"""

from datetime import UTC, datetime
from typing import Any

from app.utils.logging import get_logger

logger = get_logger(__name__)

# ── LLM severity → base score ─────────────────────────────────────────
_LLM_BASE: dict[str, int] = {
    "critical": 80,
    "high": 60,
    "medium": 40,
    "low": 20,
}

# ── Rule-based modifier weights (used on top of LLM base) ─────────────
_MOD_PROD_ENV = 8
_MOD_CORE_DEVICE = 10
_MOD_HIGH_DEPS = 5
_MOD_NO_ROLLBACK = 7
_MOD_NO_MAINT_WINDOW = 8
_MOD_INCIDENT_HIST = 5

# Action inherent severity modifiers (LLM-assisted mode)
_ACTION_MOD: dict[str, tuple[int, str]] = {
    "decommission":      (10, "Decommission permanently removes infrastructure"),
    "delete_sg":         (10, "Deleting security group removes all associated protections"),
    "firmware_upgrade":  (8,  "Firmware upgrade requires device reboot and potential outage"),
    "reboot_device":     (7,  "Device reboot causes temporary service disruption"),
    "remove_rule":       (6,  "Removing firewall rule may expose protected services"),
    "disable_rule":      (6,  "Disabling firewall rule may expose protected services"),
    "delete_vlan":       (7,  "VLAN deletion disconnects all member devices"),
    "shutdown_interface":(6,  "Interface shutdown severs connectivity"),
    "disable_port":      (4,  "Port disable may disrupt connected services"),
    "modify_rule":       (3,  "Rule modification may change traffic flow"),
    "add_rule":          (2,  "New rule addition — low risk if properly scoped"),
    "enable_port":       (2,  "Enabling port — low risk"),
    "change_vlan":       (3,  "VLAN change may move devices between segments"),
    "modify_vlan":       (3,  "VLAN modification may affect member devices"),
    "config_change":     (3,  "Configuration change — moderate risk"),
    "modify_sg":         (4,  "Security group modification may change access patterns"),
}

# Legacy raw weights (fallback when LLM is unavailable)
_LEGACY_MAX_RAW = 215
_LEGACY_ACTION_SEVERITY: dict[str, tuple[int, str]] = {
    "decommission":      (35, "Decommission permanently removes infrastructure"),
    "delete_sg":         (35, "Deleting security group removes all associated protections"),
    "firmware_upgrade":  (30, "Firmware upgrade requires device reboot and potential outage"),
    "reboot_device":     (25, "Device reboot causes temporary service disruption"),
    "remove_rule":       (20, "Removing firewall rule may expose protected services"),
    "disable_rule":      (20, "Disabling firewall rule may expose protected services"),
    "delete_vlan":       (25, "VLAN deletion disconnects all member devices"),
    "shutdown_interface":(20, "Interface shutdown severs connectivity"),
    "disable_port":      (15, "Port disable may disrupt connected services"),
    "modify_rule":       (10, "Rule modification may change traffic flow"),
    "add_rule":          (5,  "New rule addition — low risk if properly scoped"),
    "enable_port":       (5,  "Enabling port — low risk"),
    "change_vlan":       (10, "VLAN change may move devices between segments"),
    "modify_vlan":       (10, "VLAN modification may affect member devices"),
    "config_change":     (10, "Configuration change — moderate risk"),
    "modify_sg":         (15, "Security group modification may change access patterns"),
}


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _is_core_target(target_components: list[str], impact_data: dict[str, Any] | None) -> bool:
    if any("CORE" in c.upper() or "FW-" in c.upper() for c in target_components):
        return True
    if impact_data:
        for item in impact_data.get("directly_impacted", []):
            props = item.get("properties", {})
            if props.get("criticality") == "critical" or props.get("type") in ("firewall", "router"):
                return True
    return False


def _check_maintenance_window(change_data: dict[str, Any]) -> tuple[bool, str]:
    """Returns (is_risky, reason)."""
    mw_start = change_data.get("maintenance_window_start")
    mw_end = change_data.get("maintenance_window_end")
    if not mw_start or not mw_end:
        return True, "No maintenance window defined"
    if isinstance(mw_start, str):
        mw_start = datetime.fromisoformat(mw_start)
    if isinstance(mw_end, str):
        mw_end = datetime.fromisoformat(mw_end)
    mw_start = _ensure_utc(mw_start)
    mw_end = _ensure_utc(mw_end)
    now = datetime.now(UTC)
    if not (mw_start <= now <= mw_end):
        return True, "Change is outside defined maintenance window"
    return False, ""


class RiskEngine:
    async def evaluate_change(
        self,
        change_data: dict[str, Any],
        impact_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Compute a 0–100 risk score.

        Uses the LLM risk_assessment as the base when available,
        otherwise falls back to pure rule-based scoring.
        """
        llm_assessment = (impact_data or {}).get("risk_assessment", {})
        llm_severity = llm_assessment.get("severity", "").lower()
        has_llm = llm_severity in _LLM_BASE

        if has_llm:
            return await self._evaluate_llm_driven(change_data, impact_data, llm_assessment, llm_severity)
        else:
            return await self._evaluate_rule_based(change_data, impact_data)

    # ── LLM-driven scoring ─────────────────────────────────────────────
    async def _evaluate_llm_driven(
        self,
        change_data: dict[str, Any],
        impact_data: dict[str, Any] | None,
        llm_assessment: dict[str, Any],
        llm_severity: str,
    ) -> dict[str, Any]:
        factors: list[dict[str, Any]] = []
        base = _LLM_BASE[llm_severity]
        modifier = 0

        # Primary factor: LLM assessment
        llm_summary = llm_assessment.get("summary", "")
        factors.append({
            "name": "llm_risk_assessment",
            "score": base,
            "reason": f"AI assessed severity as {llm_severity}: {llm_summary[:200]}",
        })

        target_components = change_data.get("target_components", [])

        # Modifier: Production environment
        if change_data.get("environment") == "Prod":
            modifier += _MOD_PROD_ENV
            factors.append({"name": "production_environment", "score": _MOD_PROD_ENV, "reason": "Change targets Production environment"})

        # Modifier: Core / critical device
        if _is_core_target(target_components, impact_data):
            modifier += _MOD_CORE_DEVICE
            factors.append({"name": "core_network_device", "score": _MOD_CORE_DEVICE, "reason": "Change affects core/critical network device"})

        # Modifier: High dependency count
        dep_count = (impact_data or {}).get("total_dependency_count", 0)
        if dep_count > 10:
            modifier += _MOD_HIGH_DEPS
            factors.append({"name": "high_dependency_count", "score": _MOD_HIGH_DEPS, "reason": f"{dep_count} dependencies affected (>10)"})

        # Modifier: No rollback plan
        rollback = change_data.get("rollback_plan")
        if not rollback or (isinstance(rollback, str) and not rollback.strip()):
            modifier += _MOD_NO_ROLLBACK
            factors.append({"name": "no_rollback_plan", "score": _MOD_NO_ROLLBACK, "reason": "No rollback plan provided"})

        # Modifier: Outside maintenance window
        mw_risky, mw_reason = _check_maintenance_window(change_data)
        if mw_risky:
            modifier += _MOD_NO_MAINT_WINDOW
            factors.append({"name": "maintenance_window", "score": _MOD_NO_MAINT_WINDOW, "reason": mw_reason})

        # Modifier: Incident history
        incident_count = int(change_data.get("incident_history_count", 0) or 0)
        if incident_count > 0:
            modifier += _MOD_INCIDENT_HIST
            factors.append({"name": "incident_history", "score": _MOD_INCIDENT_HIST,
                            "reason": f"{incident_count} previous rolled-back changes on impacted components"})

        # Modifier: Action severity
        action = (change_data.get("action") or "").lower()
        if action in _ACTION_MOD:
            act_score, act_reason = _ACTION_MOD[action]
            modifier += act_score
            factors.append({"name": "action_severity", "score": act_score, "reason": act_reason})

        # Final score = base + modifier, capped at [0, 100]
        final_score = round(min(max(base + modifier, 0), 100), 1)

        return self._build_result(final_score, factors, base, modifier, llm_driven=True)

    # ── Legacy rule-based scoring (no LLM) ─────────────────────────────
    async def _evaluate_rule_based(
        self,
        change_data: dict[str, Any],
        impact_data: dict[str, Any] | None,
    ) -> dict[str, Any]:
        factors: list[dict[str, Any]] = []
        raw_score = 0

        env = change_data.get("environment", "")
        if env == "Prod":
            raw_score += 30
            factors.append({"name": "production_environment", "score": 30, "reason": "Change targets Production environment"})

        target_components = change_data.get("target_components", [])
        if _is_core_target(target_components, impact_data):
            raw_score += 40
            factors.append({"name": "core_network_device", "score": 40, "reason": "Change affects core/critical network device"})

        dep_count = (impact_data or {}).get("total_dependency_count", 0)
        if dep_count > 10:
            raw_score += 20
            factors.append({"name": "high_dependency_count", "score": 20, "reason": f"{dep_count} dependencies affected (>10)"})

        rollback = change_data.get("rollback_plan")
        if not rollback or (isinstance(rollback, str) and not rollback.strip()):
            raw_score += 25
            factors.append({"name": "no_rollback_plan", "score": 25, "reason": "No rollback plan provided"})

        mw_risky, mw_reason = _check_maintenance_window(change_data)
        if mw_risky:
            raw_score += 30
            factors.append({"name": "maintenance_window", "score": 30, "reason": mw_reason})

        incident_count = int(change_data.get("incident_history_count", 0) or 0)
        if incident_count > 0:
            raw_score += 15
            factors.append({"name": "incident_history", "score": 15,
                            "reason": f"{incident_count} previous rolled-back changes on impacted components"})

        action = (change_data.get("action") or "").lower()
        if action in _LEGACY_ACTION_SEVERITY:
            severity_score, severity_reason = _LEGACY_ACTION_SEVERITY[action]
            raw_score += severity_score
            factors.append({"name": "action_severity", "score": severity_score, "reason": severity_reason})

        normalized = round(min(raw_score / _LEGACY_MAX_RAW * 100, 100), 1)
        return self._build_result(normalized, factors, raw_score, 0, llm_driven=False)

    # ── Result builder ─────────────────────────────────────────────────
    @staticmethod
    def _build_result(
        score: float,
        factors: list[dict[str, Any]],
        base: int,
        modifier: int,
        llm_driven: bool,
    ) -> dict[str, Any]:
        if score <= 30:
            risk_level = "low"
            auto_approve = True
        elif score <= 70:
            risk_level = "medium"
            auto_approve = False
        else:
            risk_level = "high"
            auto_approve = False

        result = {
            "risk_score": score,
            "risk_level": risk_level,
            "auto_approve": auto_approve,
            "factors": factors,
            "llm_driven": llm_driven,
        }

        logger.info("Risk assessment: score=%.1f level=%s auto_approve=%s llm_driven=%s",
                     score, risk_level, auto_approve, llm_driven)
        return result


risk_engine = RiskEngine()
