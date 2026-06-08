from __future__ import annotations

from typing import Any


class TransportError(Exception):
    pass


class AuthenticationError(TransportError):
    pass


class TransportResult:
    def __init__(self, ok: bool, data: Any = None, error: str = ""):
        self.ok = ok
        self.data = data
        self.error = error


class BaseTransport:
    def __init__(self, host: str, port: int = 22, **kwargs: Any):
        self.host = host
        self.port = port
        self.config = kwargs

    def connect(self) -> bool:
        raise NotImplementedError

    def disconnect(self) -> None:
        raise NotImplementedError

    def run_command(self, command: str, timeout: int = 30) -> str:
        raise NotImplementedError

    def get_banner(self) -> str:
        return ""
