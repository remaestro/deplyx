from __future__ import annotations

import os
from pathlib import Path
from typing import Any

TEMPLATES_DIR = os.environ.get("TEXTFSM_TEMPLATES_DIR", "")

if not TEMPLATES_DIR:
    import ntc_templates
    TEMPLATES_DIR = str(Path(ntc_templates.__file__).resolve().parent / "templates")


class TextFSMParser:
    def __init__(self, templates_dir: str = TEMPLATES_DIR):
        self.templates_dir = templates_dir

    def parse(self, command: str, raw_output: str, os_name: str = "cisco_ios") -> list[dict[str, str]]:
        if not raw_output or not raw_output.strip():
            return []

        try:
            from textfsm import TextFSM, clitable
            from textfsm.clitable import CliTable
        except ImportError:
            return self._fallback_parse(command, raw_output)

        template_name = self._resolve_template(command, os_name)
        if not template_name:
            return self._fallback_parse(command, raw_output)

        try:
            template_path = Path(self.templates_dir) / template_name
            if not template_path.exists():
                return self._fallback_parse(command, raw_output)

            with open(template_path) as f:
                fsm = TextFSM(f)
            records = fsm.ParseText(raw_output)
            headers = fsm.header
            result = []
            for record in records:
                row = {}
                for i, h in enumerate(headers):
                    if i < len(record):
                        row[h.lower()] = record[i].strip() if record[i] else ""
                if row:
                    result.append(row)
            return result
        except Exception:
            return self._fallback_parse(command, raw_output)

    def _resolve_template(self, command: str, os_name: str) -> str | None:
        cmd_clean = command.strip().lower().replace(" ", "_")
        vendor_map = {
            "cisco_ios": "cisco_ios",
            "cisco_nxos": "cisco_nxos",
            "cisco_xr": "cisco_xr",
            "cisco_asa": "cisco_asa",
            "juniper_junos": "juniper_junos",
            "arista_eos": "arista_eos",
            "vyos": "vyos",
            "linux": "linux",
            "hp_procurve": "hp_procurve",
            "extreme_exos": "extreme_exos",
            "cisco_ios_telnet": "cisco_ios",
            "cisco_ftd": "cisco_asa",
        }
        vendor = vendor_map.get(os_name, os_name)

        candidates = [
            f"{vendor}_{cmd_clean}.textfsm",
        ]

        if "|" in cmd_clean:
            base_cmd = cmd_clean.split("|")[0].strip()
            candidates.append(f"{vendor}_{base_cmd}.textfsm")

        for template_name in candidates:
            if (Path(self.templates_dir) / template_name).exists():
                return template_name

        if "show version" in command.lower():
            for tv in ["cisco_ios", vendor]:
                if (Path(self.templates_dir) / f"{tv}_show_version.textfsm").exists():
                    return f"{tv}_show_version.textfsm"

        return None

    def _fallback_parse(self, command: str, raw_output: str) -> list[dict[str, str]]:
        return [{"raw": raw_output}]
