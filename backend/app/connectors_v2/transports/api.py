from __future__ import annotations

import os
from typing import Any

import requests
import urllib3

from .base import BaseTransport, TransportError, AuthenticationError

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API_TIMEOUT = int(os.environ.get("API_TIMEOUT", "8"))


class APITransport(BaseTransport):
    def __init__(
        self,
        host: str,
        port: int = 443,
        username: str = "",
        password: str = "",
        api_key: str = "",
        api_token: str = "",
        verify_ssl: bool = False,
        base_path: str = "/api/fdm/latest",
        **kwargs: Any,
    ):
        super().__init__(host, port, **kwargs)
        self.username = username
        self.password = password
        self.api_key = api_key
        self.api_token = api_token
        self.verify_ssl = verify_ssl
        self.base_path = base_path
        self.session = requests.Session()
        self.session.verify = verify_ssl
        self._token: str | None = None
        self._connected = False

    @property
    def _api_bases(self) -> list[str]:
        bases = [
            f"https://{self.host}:{self.port}{self.base_path}",
            f"https://{self.host}:{self.port}/api/fdm/latest",
            f"https://{self.host}:{self.port}/api/fdm/v7",
            f"https://{self.host}:{self.port}/api/fdm/v6",
        ]
        seen: list[str] = []
        for b in bases:
            if b not in seen:
                seen.append(b)
        return seen

    def connect(self) -> bool:
        if self.api_token or self.api_key:
            self._connected = True
            return True

        if self.username and self.password:
            for base in self._api_bases:
                token = self._api_login(base)
                if token:
                    self._token = token
                    self.session.headers["Authorization"] = f"Bearer {token}"
                    self.base_path = base
                    self._connected = True
                    return True

        self._connected = True
        return True

    def disconnect(self) -> None:
        self.session.close()
        self._connected = False

    def _api_login(self, api_base: str) -> str | None:
        try:
            resp = self.session.post(
                f"{api_base}/fdm/token",
                json={"grant_type": "password", "username": self.username, "password": self.password},
                timeout=API_TIMEOUT,
            )
            if resp.ok:
                data = resp.json()
                return data.get("access_token", "")
        except Exception:
            pass

        try:
            resp = self.session.post(
                f"{api_base}/fdm/token",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={"grant_type": "password", "username": self.username, "password": self.password},
                timeout=API_TIMEOUT,
            )
            if resp.ok:
                data = resp.json()
                return data.get("access_token", "")
        except Exception:
            pass

        return None

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        base = self.base_path.rstrip("/")
        url = f"{base}{path}"
        return self.session.request(method, url, timeout=API_TIMEOUT, **kwargs)

    def get(self, path: str, **kwargs: Any) -> Any:
        resp = self._request("GET", path, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def post(self, path: str, data: Any = None, **kwargs: Any) -> Any:
        resp = self._request("POST", path, json=data, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def put(self, path: str, data: Any = None, **kwargs: Any) -> Any:
        resp = self._request("PUT", path, json=data, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def delete(self, path: str, **kwargs: Any) -> Any:
        resp = self._request("DELETE", path, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def get_banner(self) -> str:
        return f"API {self.host}:{self.port}{self.base_path}"
