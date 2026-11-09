"""Failure injection, for monitoring exercises.

Disabled unless CHAOS_ENABLED=true. When enabled, `PUT /chaos` makes a service slow or flaky on purpose so
students can find the problem with metrics, logs and traces. `/healthz`, `/readyz`, `/metrics` and `/chaos`
themselves are never affected.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass

from pydantic import BaseModel, Field


class ChaosConfig(BaseModel):
    latency_ms: int = Field(0, ge=0, le=10_000, description="extra delay added to every request")
    error_rate: float = Field(0.0, ge=0.0, le=1.0, description="share of requests that fail with 500")


@dataclass
class Chaos:
    enabled: bool = False
    latency_ms: int = 0
    error_rate: float = 0.0

    def set(self, cfg: ChaosConfig) -> None:
        self.latency_ms, self.error_rate = cfg.latency_ms, cfg.error_rate

    def view(self) -> dict:
        return {"enabled": self.enabled, "latency_ms": self.latency_ms, "error_rate": self.error_rate}

    async def apply(self) -> bool:
        """Sleep if slow; return True if this request should fail."""
        if not self.enabled:
            return False
        if self.latency_ms:
            await asyncio.sleep(self.latency_ms / 1000)
        return self.error_rate > 0 and random.random() < self.error_rate  # noqa: S311  (not security related)
