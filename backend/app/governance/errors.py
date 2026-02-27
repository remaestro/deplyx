class ThresholdArtifactError(Exception):
    pass


class PolicyEvaluationError(Exception):
    pass


class PolicyStoreUnavailableError(ThresholdArtifactError):
    """Raised when PG_Policies is inaccessible or empty.

    Must never be captured silently — propagate until ``on_failure``.
    """
