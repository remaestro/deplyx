from __future__ import annotations

import json
import os
import re
from typing import Any

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


class LLMParser:
    def __init__(self, api_key: str = GEMINI_API_KEY, model: str = "gemini-2.0-flash"):
        self.api_key = api_key
        self.model = model
        self._client = None

    def is_available(self) -> bool:
        return bool(self.api_key)

    def parse_output(self, command: str, raw_output: str, device_info: dict[str, Any]) -> list[dict[str, str]]:
        if not self.is_available():
            return [{"raw": raw_output}]

        prompt = f"""You are a network device parser. Extract structured data from the command output below.

Device info: {json.dumps(device_info)}
Command: {command}

Output:
```
{raw_output[:8000]}
```

Return ONLY a JSON array of objects. Each object represents one entity (interface, route, VLAN, etc.).
Use lowercase keys. Example for interfaces:
[{{"name":"GigabitEthernet0/1","status":"up","ip":"10.0.0.1","mask":"255.255.255.0"}}]

If no structured data can be extracted, return [].
Do NOT include markdown or code fences."""
        try:
            return self._call_llm(prompt)
        except Exception:
            return [{"raw": raw_output}]

    def discover_commands(self, help_output: str, device_info: dict[str, Any]) -> list[str]:
        if not self.is_available():
            return []

        prompt = f"""You are a network expert. Given this help/output from a network device, identify the 
best commands to run to discover:
1. System version and hostname
2. Network interfaces (names, IPs, status)
3. Routing table
4. VLAN configuration (for switches)
5. Firewall rules (for firewalls)
6. BGP/OSPF neighbors (for routers)

Device info: {json.dumps(device_info)}

Help output:
```
{help_output[:6000]}
```

Return a JSON array of command strings only, ordered by priority.
Example: ["show version", "show interfaces", "show ip route", "show vlan brief"]
Do NOT include markdown or code fences."""

        try:
            return self._call_llm(prompt)
        except Exception:
            return []

    def _call_llm(self, prompt: str) -> Any:
        import google.generativeai as genai

        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(self.model)
        response = model.generate_content(prompt)
        text = response.text.strip()

        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

        return json.loads(text)
