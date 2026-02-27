"""Unit tests for governance — ThresholdArtifact and ThresholdConfig."""

import pytest

from app.governance.threshold_artifact import ThresholdConfig
from app.governance.errors import (
    PolicyStoreUnavailableError,
    ThresholdArtifactError,
    PolicyEvaluationError,
)


class TestThresholdConfig:
    def test_default_values(self):
        tc = ThresholdConfig(auto_approve_max=20, targeted_max=60, cab_min=61)
        assert tc.auto_approve_max == 20
        assert tc.targeted_max == 60
        assert tc.cab_min == 61

    def test_threshold_ordering_constraint(self):
        """Spec says auto_approve_max < targeted_max <= cab_min."""
        tc = ThresholdConfig(auto_approve_max=20, targeted_max=60, cab_min=61)
        assert tc.auto_approve_max < tc.targeted_max
        assert tc.targeted_max <= tc.cab_min


class TestGovernanceErrors:
    def test_policy_store_unavailable_hierarchy(self):
        assert issubclass(PolicyStoreUnavailableError, ThresholdArtifactError)

    def test_policy_evaluation_exists(self):
        err = PolicyEvaluationError("eval failed")
        assert str(err) == "eval failed"

    def test_threshold_artifact_base(self):
        err = ThresholdArtifactError("base")
        assert isinstance(err, Exception)
