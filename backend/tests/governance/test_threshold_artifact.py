import json

import pytest

from app.governance.errors import ThresholdArtifactError
from app.governance.threshold_artifact import load_threshold_artifact


def test_load_threshold_artifact_defaults(monkeypatch):
    monkeypatch.setattr("app.governance.threshold_artifact.settings.governance_threshold_artifact", "")
    artifact = load_threshold_artifact()
    assert artifact.level_for_score(20) == "low"
    assert artifact.level_for_score(50) == "medium"
    assert artifact.level_for_score(95) == "high"


def test_load_threshold_artifact_from_file(tmp_path, monkeypatch):
    p = tmp_path / "thresholds.json"
    p.write_text(json.dumps({"low_max": 25, "medium_max": 60}))
    monkeypatch.setattr("app.governance.threshold_artifact.settings.governance_threshold_artifact", str(p))
    artifact = load_threshold_artifact()
    assert artifact.level_for_score(26) == "medium"


def test_load_threshold_artifact_missing_file(monkeypatch):
    monkeypatch.setattr("app.governance.threshold_artifact.settings.governance_threshold_artifact", "/nope/missing.json")
    with pytest.raises(ThresholdArtifactError):
        load_threshold_artifact()
