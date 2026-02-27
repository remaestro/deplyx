"""Unit tests for the pipeline tasks and dead-letter queue."""

import json

import pytest

from app.tasks.pipeline.errors import PipelineError, TransientError, ChangeNotFoundError


class TestPipelineErrorHierarchy:
    def test_transient_is_pipeline(self):
        assert issubclass(TransientError, PipelineError)

    def test_change_not_found_is_pipeline(self):
        assert issubclass(ChangeNotFoundError, PipelineError)

    def test_transient_can_be_raised(self):
        with pytest.raises(TransientError):
            raise TransientError("temporary failure")

    def test_pipeline_error_message(self):
        err = PipelineError("boom")
        assert str(err) == "boom"


class TestDeadLetterConstants:
    def test_key(self):
        from app.tasks.poll_dead_letter import DEAD_LETTER_KEY

        assert DEAD_LETTER_KEY == "deplyx:dead_letter_queue"

    def test_max_attempts_positive(self):
        from app.tasks.poll_dead_letter import MAX_ATTEMPTS

        assert MAX_ATTEMPTS >= 1


class TestDeadLetterRedisClient:
    """Verify _get_redis returns a callable factory."""

    def test_get_redis_callable(self):
        from app.tasks.poll_dead_letter import _get_redis

        assert callable(_get_redis)


class TestReconcileTask:
    def test_drift_count_default(self):
        from app.tasks.reconcile_graph_pg import get_last_drift_count

        assert isinstance(get_last_drift_count(), int)
        assert get_last_drift_count() >= 0
