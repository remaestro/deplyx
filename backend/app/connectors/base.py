from abc import ABC
from typing import Any


class BaseConnector(ABC):
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        operation = (request or {}).get("operation")
        payload = (request or {}).get("input") or {}

        if operation == "sync":
            return await self.sync()
        if operation == "validate":
            return await self.validate_change(payload)
        if operation == "simulate":
            return await self.simulate_change(payload)
        if operation == "apply":
            return await self.apply_change(payload)

        return {
            "status": "error",
            "error": f"Unsupported connector operation: {operation}",
        }

    async def sync(self) -> dict[str, Any]:
        raise NotImplementedError

    async def validate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    async def simulate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    async def apply_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError
