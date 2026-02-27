class PipelineError(Exception):
    pass


class TransientError(PipelineError):
    """Raised for transient failures (Neo4j down, temporary network error).

    Celery ``autoretry_for`` should include this class so the task is
    automatically retried with exponential back-off.
    """


class ChangeNotFoundError(PipelineError):
    pass
