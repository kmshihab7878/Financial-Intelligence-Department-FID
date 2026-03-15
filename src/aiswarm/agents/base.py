from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class Agent(ABC):
    def __init__(self, agent_id: str, cluster: str) -> None:
        self.agent_id = agent_id
        self.cluster = cluster

    @abstractmethod
    def analyze(self, context: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def propose(self, context: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def validate(self, context: dict[str, Any]) -> bool:
        raise NotImplementedError
