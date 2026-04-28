"""Webhook receiver — parse, verify, and dispatch incoming webhook events."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Callable

from .exceptions import PayloadError
from .models import WebhookEvent
from .verifiers import BaseVerifier


class WebhookReceiver:
    """Receives and dispatches webhook events.

    Optionally verifies signatures before processing.
    Supports registering handlers for specific event types.
    """

    def __init__(self, verifier: BaseVerifier | None = None):
        self.verifier = verifier
        self._handlers: dict[str, list[Callable]] = defaultdict(list)

    def on(self, event_type: str, handler: Callable[[WebhookEvent], Any]) -> None:
        """Register a handler for a specific event type.

        Multiple handlers can be registered for the same event type.
        """
        self._handlers[event_type].append(handler)

    def receive(self, payload: bytes, headers: dict[str, str]) -> WebhookEvent:
        """Verify and parse an incoming webhook payload into a WebhookEvent.

        If a verifier is configured, the signature is checked first.
        Raises PayloadError if the payload cannot be parsed.
        Raises SignatureVerificationError if verification fails.
        """
        if self.verifier:
            self.verifier.verify_or_raise(payload, headers)

        try:
            data = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise PayloadError(f"Invalid JSON payload: {e}") from e

        if not isinstance(data, dict):
            raise PayloadError("Payload must be a JSON object")

        return WebhookEvent(
            id=data.get("id", ""),
            type=data.get("type", ""),
            timestamp=data.get("timestamp", 0.0),
            payload=data.get("payload", data),
            metadata=data.get("metadata", {}),
        )

    def dispatch(self, event: WebhookEvent) -> list[Any]:
        """Route an event to all registered handlers for its type.

        Also invokes handlers registered with "*" (wildcard) for all events.
        Returns a list of handler return values.
        """
        results = []
        for handler in self._handlers.get(event.type, []):
            results.append(handler(event))
        for handler in self._handlers.get("*", []):
            results.append(handler(event))
        return results

    def process(self, payload: bytes, headers: dict[str, str]) -> WebhookEvent:
        """Verify, parse, and dispatch a webhook in one step.

        Combines receive() and dispatch().
        """
        event = self.receive(payload, headers)
        self.dispatch(event)
        return event
