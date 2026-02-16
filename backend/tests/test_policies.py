"""Tests for policy evaluation."""

import pytest

from app.services.policy_service import _check_time_restriction, _check_double_validation, _check_auto_block
from app.models.policy import Policy


class FakeChange:
    """Minimal change-like object for testing."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def _make_policy(**kwargs) -> Policy:
    defaults = dict(
        id=1, name="Test", description="", rule_type="time_restriction",
        condition={}, action="block", enabled=True, created_by=None,
    )
    defaults.update(kwargs)
    return Policy(**defaults)


def test_auto_block_any_any() -> None:
    policy = _make_policy(
        rule_type="auto_block",
        condition={"block_any_any_rules": True},
    )
    change = FakeChange(
        environment="production",
        change_type="firewall_rule",
        description="Add rule with source any destination 0.0.0.0/0",
        execution_plan="",
    )
    result = _check_auto_block(policy, change)
    assert result.triggered is True
    assert "ANY-ANY" in result.reason


def test_auto_block_not_triggered() -> None:
    policy = _make_policy(
        rule_type="auto_block",
        condition={"block_any_any_rules": True},
    )
    change = FakeChange(
        environment="staging",
        change_type="vlan",
        description="Change VLAN assignment",
        execution_plan="",
    )
    result = _check_auto_block(policy, change)
    assert result.triggered is False


def test_double_validation_triggered() -> None:
    policy = _make_policy(
        rule_type="double_validation",
        condition={
            "environments": ["production"],
            "change_types": ["firewall_rule"],
            "required_approvals": 2,
        },
    )
    change = FakeChange(environment="production", change_type="firewall_rule")
    result = _check_double_validation(policy, change)
    assert result.triggered is True
    assert "2 approvals" in result.reason


def test_double_validation_not_triggered() -> None:
    policy = _make_policy(
        rule_type="double_validation",
        condition={"environments": ["production"], "change_types": ["firewall_rule"]},
    )
    change = FakeChange(environment="staging", change_type="vlan")
    result = _check_double_validation(policy, change)
    assert result.triggered is False
