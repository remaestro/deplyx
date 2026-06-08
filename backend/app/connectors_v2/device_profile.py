from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

PROFILES_DIR = Path(__file__).resolve().parent / "profiles"

_PROFILE_CACHE: dict[str, "DeviceProfile"] | None = None


def _clean_version(raw: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]", "", raw.strip())


def _fingerprint_from_banner(banner: str) -> dict[str, str | None]:
    banner_lower = banner.lower()
    result: dict[str, str | None] = {
        "vendor": None,
        "os": None,
        "os_version": None,
        "hostname": None,
        "model": None,
    }

    if "ssh-" in banner_lower:
        result["vendor"] = "generic"

    if "cisco" in banner_lower:
        result["vendor"] = "cisco"
        if "ftd" in banner_lower:
            result["os"] = "ftd"
        elif "ios" in banner_lower and "nx-os" not in banner_lower:
            result["os"] = "ios"
        elif "nx-os" in banner_lower:
            result["os"] = "nxos"
        elif "asa" in banner_lower:
            result["os"] = "asa"

    elif "juniper" in banner_lower:
        result["vendor"] = "juniper"
        result["os"] = "junos"

    elif "palo alto" in banner_lower or "panos" in banner_lower:
        result["vendor"] = "paloalto"
        result["os"] = "panos"

    elif "fortinet" in banner_lower or "fortigate" in banner_lower:
        result["vendor"] = "fortinet"
        result["os"] = "fortios"

    elif "vyatta" in banner_lower or "vyos" in banner_lower:
        result["vendor"] = "vyos"
        result["os"] = "vyos"

    elif "aruba" in banner_lower:
        result["vendor"] = "aruba"
        result["os"] = "aruba"

    elif "checkpoint" in banner_lower:
        result["vendor"] = "checkpoint"
        result["os"] = "checkpoint"

    elif "linux" in banner_lower:
        result["vendor"] = "linux"

    return result


def _fingerprint_from_ssh_cmd(ssh_transport: Any) -> dict[str, str | None]:
    result: dict[str, str | None] = {
        "vendor": None,
        "os": None,
        "os_version": None,
        "hostname": None,
        "model": None,
    }

    probes = ["show version", "show system info", "show sysinfo", "display version", "get system", "uname -a"]
    for cmd in probes:
        try:
            out = ssh_transport.run_command(cmd)
            if not out.strip():
                continue
            lower = out.lower()
            if "cisco" in lower or "ios" in lower:
                result["vendor"] = "cisco"
                if "nx-os" in lower or "nxos" in lower:
                    result["os"] = "nxos"
                elif "ftd" in lower or "firepower" in lower:
                    result["os"] = "ftd"
                elif "asa" in lower:
                    result["os"] = "asa"
                else:
                    result["os"] = "ios"
                m = re.search(r"Version\s+([\d.]+)", out, re.IGNORECASE)
                if m:
                    result["os_version"] = _clean_version(m.group(1))
                m = re.search(r"Processor board ID\s+(\S+)", out, re.IGNORECASE)
                if m:
                    result["model"] = m.group(1)
                m = re.search(r"(\S+)\s+uptime", out, re.IGNORECASE)
                if m:
                    result["hostname"] = m.group(1)
                return result
            if "junos" in lower:
                result["vendor"] = "juniper"
                result["os"] = "junos"
                m = re.search(r"Junos:\s*([\d.]+)", out, re.IGNORECASE)
                if m:
                    result["os_version"] = _clean_version(m.group(1))
                return result
            if "vyos" in lower or "vyatta" in lower:
                result["vendor"] = "vyos"
                result["os"] = "vyos"
                m = re.search(r"Version:\s*(\S+)", out, re.IGNORECASE)
                if m:
                    result["os_version"] = _clean_version(m.group(1))
                return result
            if "fortinet" in lower or "fortigate" in lower:
                result["vendor"] = "fortinet"
                result["os"] = "fortios"
                return result
            if "palo" in lower or "panos" in lower:
                result["vendor"] = "paloalto"
                result["os"] = "panos"
                return result
            if "linux" in lower:
                result["vendor"] = "linux"
                m = re.search(r"PRETTY_NAME=[\"']?(.+?)[\"']?$", out, re.MULTILINE)
                if m:
                    result["os"] = "linux"
                    result["os_version"] = _clean_version(m.group(1))
                return result
            if "aruba" in lower:
                result["vendor"] = "aruba"
                result["os"] = "aruba"
                return result
        except Exception:
            continue
    return result


def fingerprint_device(
    host: str,
    port: int = 22,
    username: str = "",
    password: str = "",
    api_username: str = "",
    api_password: str = "",
) -> dict[str, Any]:
    from app.connectors_v2.transports import SSHTransport, APITransport

    result: dict[str, Any] = {
        "vendor": None,
        "os": None,
        "os_version": None,
        "hostname": None,
        "model": None,
        "transport": None,
        "api_version": None,
        "source": "unknown",
    }

    if password:
        try:
            ssh = SSHTransport(host, port=port, username=username, password=password)
            banner = ssh.get_banner()
            if banner:
                result.update(_fingerprint_from_banner(banner))
                result["transport"] = "ssh"
                result["source"] = "banner"

            cmd_fp = _fingerprint_from_ssh_cmd(ssh)
            if cmd_fp.get("vendor"):
                result.update(cmd_fp)
                result["transport"] = "ssh"
                result["source"] = "ssh_command"
            ssh.close()
        except Exception:
            pass

    needs_api = not result.get("vendor")
    if needs_api and result.get("os") == "ftd":
        try:
            api = APITransport(host, username=api_username or username, password=api_password or password)
            try:
                import requests as req
                resp = req.post(f"https://{host}/api/fdm/latest/fdm/token",
                                json={"grant_type": "password", "username": api_username or username,
                                       "password": api_password or password},
                                verify=False, timeout=5)
                if resp.ok:
                    result["vendor"] = "cisco"
                    result["os"] = "ftd"
                    result["transport"] = "api"
                    result["source"] = "fdm_api"
                    result["api_version"] = "latest"
            except Exception:
                pass
        except Exception:
            pass

    if not result.get("vendor"):
        try:
            api = APITransport(host, username=username, password=password)
            for base in [
                f"https://{host}/api/?type=op&cmd=<show><system><info></info></system></show>",
                f"https://{host}/api/v2/monitor/system/status",
            ]:
                try:
                    resp = api.session.get(base, verify=False, timeout=5)
                    if resp.ok:
                        result["vendor"] = "unknown"
                        result["transport"] = "api"
                        result["source"] = "api_probe"
                        break
                except Exception:
                    continue
        except Exception:
            pass

    return result


_PROFILE_SCHEMA = {
    "name": str,
    "vendor": str,
    "os": str,
    "transports": list,
    "commands": dict,
    "command_groups": dict,
}


class DeviceProfile:
    def __init__(self, data: dict[str, Any]):
        errors = self._validate(data)
        if errors:
            raise ValueError(f"Invalid profile {data.get('name', '?')}: {errors}")
        self.name: str = data.get("name", "unknown")
        self.vendor: str = data.get("vendor", "")
        self.os: str = data.get("os", "")
        self.match_banner: list[str] = data.get("match_banner", [])
        self.match_cmd_output: list[str] = data.get("match_cmd_output", [])
        self.transports: list[dict[str, Any]] = data.get("transports", [])
        self.commands: dict[str, Any] = data.get("commands", {})
        self.command_groups: dict[str, Any] = data.get("command_groups", {})
        self.parsers: dict[str, str] = data.get("parsers", {})
        self.neo4j_labels: dict[str, str] = data.get("neo4j_labels", {})
        self.api_discovery: list[str] = data.get("api_discovery", [])
        self.fallback: dict[str, Any] = data.get("fallback", {})

    @staticmethod
    def _validate(data: dict[str, Any]) -> list[str]:
        errs = []
        for key, expected_type in _PROFILE_SCHEMA.items():
            val = data.get(key)
            if val is not None and not isinstance(val, expected_type):
                errs.append(f"{key}: expected {expected_type.__name__}, got {type(val).__name__}")
        if data.get("transports"):
            for i, t in enumerate(data["transports"]):
                if not isinstance(t, dict) or "type" not in t:
                    errs.append(f"transports[{i}]: missing 'type' field")
                if t.get("type") == "ssh" and not t.get("device_type"):
                    errs.append(f"transports[{i}]: ssh transport missing 'device_type'")
                if not isinstance(t.get("priority", 0), (int, float)):
                    errs.append(f"transports[{i}]: priority must be a number")
        if data.get("command_groups"):
            for gname, g in data["command_groups"].items():
                if not isinstance(g, dict):
                    errs.append(f"command_groups.{gname}: must be a dict")
        return errs

    def matches_fingerprint(self, fp: dict[str, Any]) -> bool:
        if self.vendor and self.vendor != fp.get("vendor"):
            return False
        if self.os and not fp.get("os"):
            return False
        if self.os and self.os != fp.get("os"):
            return False
        return True

    def get_commands_for_group(self, group: str) -> list[str]:
        group_def = self.command_groups.get(group, {})
        cmds = list(group_def.get("commands", []))
        for cmd_name in group_def.get("refs", []):
            if cmd_name in self.commands:
                cmds.append(self.commands[cmd_name])
        return cmds

    def get_all_command_groups(self) -> list[str]:
        return list(self.command_groups.keys())

    @staticmethod
    def load_all(profiles_dir: str | Path | None = None) -> dict[str, "DeviceProfile"]:
        global _PROFILE_CACHE
        if _PROFILE_CACHE is not None and profiles_dir is None:
            return _PROFILE_CACHE

        d = Path(profiles_dir) if profiles_dir else PROFILES_DIR
        profiles: dict[str, DeviceProfile] = {}
        if not d.exists():
            return profiles
        for f in sorted(d.glob("*.yml")):
            with open(f) as fh:
                data = yaml.safe_load(fh)
            if data and data.get("name"):
                profiles[data["name"]] = DeviceProfile(data)
        if profiles_dir is None:
            _PROFILE_CACHE = profiles
        return profiles

    @staticmethod
    def find_match(fp: dict[str, Any], profiles: dict[str, "DeviceProfile"]) -> "DeviceProfile | None":
        scored = []
        for name, profile in profiles.items():
            score = 0
            if profile.matches_fingerprint(fp):
                score += 1
            if profile.vendor and profile.vendor == fp.get("vendor"):
                score += 2
            if profile.os and profile.os == fp.get("os"):
                score += 3
            scored.append((score, name, profile))
        scored.sort(key=lambda x: -x[0])
        if scored and scored[0][0] > 0:
            return scored[0][2]
        return None
