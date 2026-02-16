from abc import ABC, abstractmethod
from typing import Any


class BaseConnector(ABC):
    @abstractmethod
    async def sync(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def validate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def simulate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def apply_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError
