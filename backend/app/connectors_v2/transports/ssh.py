from __future__ import annotations

import os
import time
from typing import Any

from .base import BaseTransport, TransportError, AuthenticationError

_LEGACY_KEX = {"disabled_algorithms": {"pubkeys": ["rsa-sha2-256", "rsa-sha2-512"]}}

CONN_TIMEOUT = int(os.environ.get("SSH_CONN_TIMEOUT", "8"))
CMD_TIMEOUT = int(os.environ.get("SSH_CMD_TIMEOUT", "15"))
BANNER_TIMEOUT = int(os.environ.get("SSH_BANNER_TIMEOUT", "8"))
AUTH_TIMEOUT = int(os.environ.get("SSH_AUTH_TIMEOUT", "8"))


class SSHTransport(BaseTransport):
    def __init__(
        self,
        host: str,
        port: int = 22,
        username: str = "",
        password: str = "",
        enable_password: str | None = None,
        device_type: str | None = None,
        conn_timeout: int = CONN_TIMEOUT,
        cmd_timeout: int = CMD_TIMEOUT,
        **kwargs: Any,
    ):
        super().__init__(host, port, **kwargs)
        self.username = username
        self.password = password
        self.enable_password = enable_password or password
        self.device_type = device_type
        self.conn_timeout = conn_timeout
        self.cmd_timeout = cmd_timeout
        self._conn = None
        self._last_error: str | None = None
        self._backoff_until: float = 0

    def connect(self) -> bool:
        if self._backoff_until > time.time():
            self._last_error = f"Rate limited until {self._backoff_until:.0f}"
            return False

        from netmiko import ConnectHandler
        from netmiko.exceptions import NetMikoAuthenticationException, NetMikoTimeoutException

        params: dict[str, Any] = {
            "device_type": "unknown",
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "password": self.password,
            "secret": self.enable_password,
            "conn_timeout": self.conn_timeout,
            "timeout": self.conn_timeout + 5,
            "banner_timeout": BANNER_TIMEOUT,
            "auth_timeout": AUTH_TIMEOUT,
            "fast_cli": False,
            "session_log": None,
            "global_cmd_verify": False,
        }

        if "telnet" not in (self.device_type or ""):
            params.update(_LEGACY_KEX)

        candidates = self._candidates()
        last_error: Exception | None = None

        for dtype in candidates:
            params["device_type"] = dtype
            params["global_cmd_verify"] = "telnet" not in dtype
            try:
                self._conn = ConnectHandler(**params)
                self.device_type = dtype
                ok, err = self._healthcheck()
                if ok:
                    return True
                self._conn = None
                last_error = Exception(err or "healthcheck failed")
            except NetMikoAuthenticationException:
                self._backoff_until = time.time() + 30
                raise AuthenticationError(f"SSH auth failed for {self.host} as {self.username}")
            except NetMikoTimeoutException as e:
                last_error = e
                continue
            except Exception as e:
                last_error = e
                continue

        self._backoff_until = time.time() + 15
        if last_error:
            self._last_error = str(last_error)
            raise TransportError(f"Cannot connect to {self.host}:{self.port}: {last_error}")
        return False

    def _candidates(self) -> list[str]:
        if self.device_type:
            primary = self.device_type
            if "_telnet" in primary:
                return [primary]
            return [primary, f"{primary}_telnet"]
        return [
            "cisco_ftd", "cisco_ftd_ssh", "cisco_asa",
            "cisco_ios", "cisco_ios_telnet",
            "cisco_xr", "cisco_nxos",
            "juniper_junos", "arista_eos", "linux",
            "vyos", "extreme_exos",
            "hp_procurve", "huawei",
        ]

    def _healthcheck(self, max_retry: int = 2) -> tuple[bool, str]:
        if not self._conn:
            return False, "not connected"
        for cmd in ["show version", "show clock", "show system info", "hostname"]:
            for attempt in range(max_retry):
                try:
                    out = self._conn.send_command(cmd, read_timeout=5)
                    if out and len(out.strip()) > 10:
                        return True, ""
                except Exception:
                    time.sleep(0.5 * (attempt + 1))
        return False, f"healthcheck: no command produced output"

    def disconnect(self) -> None:
        if self._conn:
            try:
                self._conn.disconnect()
            except Exception:
                pass
            self._conn = None

    def run_command(self, command: str, timeout: int | None = None) -> str:
        if not self._conn:
            self.connect()
        t = timeout or self.cmd_timeout
        try:
            return self._conn.send_command_timing(command, read_timeout=t)
        except Exception:
            try:
                self._conn.write_channel(command + "\n")
                time.sleep(1)
                out = self._conn.read_channel()
                time.sleep(0.5)
                out += self._conn.read_channel()
                return out.strip()
            except Exception as e:
                raise TransportError(f"Command failed: {command[:50]}: {e}")

    def send_command(self, command: str, timeout: int | None = None, **kwargs: Any) -> str:
        if not self._conn:
            raise TransportError("Not connected")
        t = timeout or self.cmd_timeout
        for attempt in range(3):
            try:
                return self._conn.send_command(command, read_timeout=t, **kwargs)
            except Exception:
                try:
                    return self._conn.send_command(command, read_timeout=t, cmd_verify=False, **kwargs)
                except Exception:
                    try:
                        return self._conn.send_command_timing(command, read_timeout=t)
                    except Exception:
                        continue
        raise TransportError(f"send_command failed: {command[:50]} (3 attempts)")

    def send_command_timing(self, command: str, timeout: int | None = None) -> str:
        if not self._conn:
            raise TransportError("Not connected")
        t = timeout or self.cmd_timeout
        try:
            return self._conn.send_command_timing(command, read_timeout=t)
        except Exception as e:
            raise TransportError(f"send_command_timing failed: {command[:50]}: {e}")

    def send_config_set(self, commands: list[str]) -> str:
        if not self._conn:
            raise TransportError("Not connected")
        try:
            return self._conn.send_config_set(commands)
        except Exception as e:
            raise TransportError(f"send_config_set failed: {e}")

    def get_banner(self) -> str:
        import socket
        try:
            s = socket.socket()
            s.settimeout(5)
            s.connect((self.host, self.port))
            banner = s.recv(4096).decode(errors="ignore")
            s.close()
            return banner.strip()
        except Exception:
            return ""

    def enable_mode(self) -> bool:
        if not self._conn:
            return False
        try:
            self._conn.enable()
            return True
        except Exception:
            return False
