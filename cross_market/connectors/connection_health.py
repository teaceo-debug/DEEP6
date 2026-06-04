"""Health check registry — aggregates all connector states."""
from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict


class HealthStatus(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


@dataclass
class ConnectorHealth:
    name: str
    connected: bool = False
    last_message_ts: float = 0.0
    message_rate: float = 0.0
    error_count: int = 0
    latency_ms: float = 0.0

    @property
    def status(self) -> HealthStatus:
        age = time.time() - self.last_message_ts
        if not self.connected or age > 60:
            return HealthStatus.RED
        if age > 10 or self.error_count > 5:
            return HealthStatus.YELLOW
        return HealthStatus.GREEN


class ConnectionHealthRegistry:
    def __init__(self):
        self._connectors: Dict[str, ConnectorHealth] = {}

    def register(self, name: str) -> ConnectorHealth:
        h = ConnectorHealth(name=name)
        self._connectors[name] = h
        return h

    def update(
        self,
        name: str,
        connected: bool = True,
        latency_ms: float = 0.0,
    ) -> None:
        if name not in self._connectors:
            self.register(name)
        h = self._connectors[name]
        h.connected = connected
        h.last_message_ts = time.time()
        h.latency_ms = latency_ms

    @property
    def overall(self) -> HealthStatus:
        if not self._connectors:
            return HealthStatus.RED
        statuses = [h.status for h in self._connectors.values()]
        if any(s == HealthStatus.RED for s in statuses):
            return HealthStatus.RED
        if any(s == HealthStatus.YELLOW for s in statuses):
            return HealthStatus.YELLOW
        return HealthStatus.GREEN

    def summary(self) -> dict:
        return {
            "overall": self.overall.value,
            "connectors": {
                name: {
                    "status": h.status.value,
                    "connected": h.connected,
                    "latency_ms": h.latency_ms,
                }
                for name, h in self._connectors.items()
            },
        }
