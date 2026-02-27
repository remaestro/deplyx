"""ThresholdArtifact — frontière de code absolue pour les seuils de politique.

Ce module est le **seul** autorisé à lire PG_Policies pour des valeurs de seuil.
Cette règle est vérifiée par un test structurel automatisé.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.governance.errors import (
    PolicyEvaluationError,
    PolicyStoreUnavailableError,
    ThresholdArtifactError,
)

_DEFAULT_THRESHOLDS = {
    "low_max": 30,
    "medium_max": 70,
}


@dataclass
class ThresholdConfig:
    """Routing-band boundaries."""

    auto_approve_max: int  # score ≤ this → auto-approval
    targeted_max: int      # score ≤ this → targeted approval
    cab_min: int           # score ≥ this → CAB required


class ThresholdArtifact:
    def __init__(self, low_max: int, medium_max: int) -> None:
        self.low_max = low_max
        self.medium_max = medium_max

    def level_for_score(self, score: float) -> str:
        if score <= self.low_max:
            return "low"
        if score <= self.medium_max:
            return "medium"
        return "high"

    def get_thresholds(self) -> ThresholdConfig:
        """Return a ``ThresholdConfig`` derived from the loaded boundaries."""
        return ThresholdConfig(
            auto_approve_max=self.low_max,
            targeted_max=self.medium_max,
            cab_min=self.medium_max + 1,
        )


async def get_thresholds_from_db(db: Any) -> ThresholdConfig:
    """Read thresholds from PG_Policies (policies table).

    Raises ``PolicyStoreUnavailableError`` if the DB is unreachable or
    contains no active policy configuration.
    """
    try:
        from sqlalchemy import select
        from app.models.policy import Policy

        result = await db.execute(
            select(Policy).where(Policy.name == "workflow_thresholds", Policy.enabled.is_(True))
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise PolicyStoreUnavailableError("No active policy configuration found")

        condition = row.condition or {}
        low_max = int(condition.get("low_max", _DEFAULT_THRESHOLDS["low_max"]))
        medium_max = int(condition.get("medium_max", _DEFAULT_THRESHOLDS["medium_max"]))
        return ThresholdConfig(
            auto_approve_max=low_max,
            targeted_max=medium_max,
            cab_min=medium_max + 1,
        )
    except PolicyStoreUnavailableError:
        raise
    except Exception as exc:
        raise PolicyStoreUnavailableError(f"Policy store unavailable: {exc}") from exc


def load_threshold_artifact() -> ThresholdArtifact:
    path = (settings.governance_threshold_artifact or "").strip()
    if not path:
        return ThresholdArtifact(**_DEFAULT_THRESHOLDS)

    artifact_path = Path(path)
    if not artifact_path.exists():
        raise ThresholdArtifactError(f"Threshold artifact not found: {path}")

    try:
        data: dict[str, Any] = json.loads(artifact_path.read_text())
        low_max = int(data.get("low_max", _DEFAULT_THRESHOLDS["low_max"]))
        medium_max = int(data.get("medium_max", _DEFAULT_THRESHOLDS["medium_max"]))
    except Exception as exc:
        raise ThresholdArtifactError(f"Invalid threshold artifact: {exc}") from exc

    if low_max < 0 or medium_max < low_max:
        raise PolicyEvaluationError("Invalid threshold ordering")

    return ThresholdArtifact(low_max=low_max, medium_max=medium_max)
