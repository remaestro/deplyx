"""Lightweight HTTP health server for lab mock devices.

Runs on port 8080 inside each mock container.  The ``/health`` endpoint
returns {"status": "ok"} plus a snapshot of the current DeviceState.

Usage in a mock entrypoint::

    from shared.state import DeviceState
    from shared.health_server import start_health_server

    state = DeviceState()
    start_health_server(state)  # non-blocking (daemon thread)
"""

import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared.state import DeviceState

_DEFAULT_PORT = 8080


class _HealthHandler(BaseHTTPRequestHandler):
    state: "DeviceState"

    def do_GET(self):
        if self.path == "/health":
            body = json.dumps({"status": "ok", **self.state.as_dict()})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):  # noqa: A002
        pass  # suppress request logs


def start_health_server(
    state: "DeviceState",
    port: int = _DEFAULT_PORT,
) -> threading.Thread:
    """Start the health HTTP server in a daemon thread.

    Returns the ``threading.Thread`` (already started).
    """

    handler_cls = type(
        "_BoundHealthHandler",
        (_HealthHandler,),
        {"state": state},
    )

    server = HTTPServer(("0.0.0.0", port), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread
