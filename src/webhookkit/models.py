"""Webhook data models."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class WebhookEvent:
    """Represents a webhook event."""

    type: str
    payload: dict[str, Any]
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "metadata": self.metadata,
        }


@dataclass
class RetryPolicy:
    """Configuration for webhook delivery retry behavior."""

    max_retries: int = 3
    backoff: str = "exponential"
    initial_delay: float = 1.0
    max_delay: float = 60.0
    jitter: bool = True


@dataclass
class WebhookDelivery:
    """Record of a single webhook delivery attempt."""

    event: WebhookEvent
    url: str
    status_code: int | None = None
    response_body: str = ""
    attempt: int = 1
    success: bool = False
    duration_ms: float = 0.0


@dataclass
class DeliveryResult:
    """Aggregate result of a webhook delivery (including retries)."""

    deliveries: list[WebhookDelivery] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return any(d.success for d in self.deliveries)

    @property
    def total_attempts(self) -> int:
        return len(self.deliveries)
