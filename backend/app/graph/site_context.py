"""Request/task-scoped site context for tagging and filtering Neo4j data.

During a connector sync we set ``current_site_id`` so that every node merged
into the graph is automatically tagged with its owning site. Read queries use
the same value (or an explicit argument) to scope topology to a single site.
"""
from contextlib import contextmanager
from contextvars import ContextVar

current_site_id: ContextVar[int | None] = ContextVar("current_site_id", default=None)


@contextmanager
def site_scope(site_id: int | None):
    token = current_site_id.set(site_id)
    try:
        yield
    finally:
        current_site_id.reset(token)
