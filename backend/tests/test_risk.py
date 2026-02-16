"""Tests for risk scoring engine."""

import pytest

from app.risk.engine import risk_engine


@pytest.mark.asyncio
async def test_risk_score_low() -> None:
    """Non-production, few deps, has rollback = low risk."""
    result = await risk_engine.evaluate_change(
        change_data={
            "environment": "lab",
            "rollback_plan": "Revert config",
            "maintenance_window_start": None,
            "maintenance_window_end": None,
            "target_components": [],
        },
        impact_data={"directly_impacted": [], "total_dependency_count": 2},
    )
    # Lab env: no prod (+0), no core device (+0), <10 deps (+0),
    # has rollback (+0), but no maintenance window (+30) => raw 30 => norm ~18.75
    assert result["risk_score"] <= 30
    assert result["risk_level"] == "low"


@pytest.mark.asyncio
async def test_risk_score_high() -> None:
    """Production, core device, many deps, no rollback, outside window = high risk."""
    result = await risk_engine.evaluate_change(
        change_data={
            "environment": "Prod",
            "rollback_plan": "",
            "maintenance_window_start": "2020-01-01T00:00:00+00:00",
            "maintenance_window_end": "2020-01-01T01:00:00+00:00",
            "target_components": ["FW-01"],
        },
        impact_data={
            "directly_impacted": [
                {"properties": {"criticality": "critical", "type": "firewall"}},
            ],
            "total_dependency_count": 15,
        },
    )
    # Prod (+30) + core (+40) + >10 deps (+20) + no rollback (+25) + outside window (+30) = 145
    # norm = 145/160*100 = 90.6
    assert result["risk_score"] > 70
    assert result["risk_level"] == "high"


@pytest.mark.asyncio
async def test_risk_factors_returned() -> None:
    """Verify the factors list is populated."""
    result = await risk_engine.evaluate_change(
        change_data={"environment": "Prod", "target_components": []},
    )
    assert isinstance(result["factors"], list)
    assert len(result["factors"]) > 0
