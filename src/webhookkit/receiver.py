"""Webhook receiver — parse, verify, and dispatch incoming webhook events."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any, Callable

from .exceptions import PayloadError
from .models import WebhookEvent
from .verifiers import BaseVerifier

logger = logging.getLogger("webhookkit.receiver")


class WebhookReceiver:
    """Receives and dispatches webhook events.

    Optionally verifies signatures before processing.
    Supports registering handlers for specific event types.
    """

    def __init__(
        self,
        verifier: BaseVerifier | None = None,
        on_error: Callable[[Exception, WebhookEvent, Callable], Any] | None = None,
    ):
        self.verifier = verifier
        self._handlers: dict[str, list[Callable]] = defaultdict(list)
        self._on_error = on_error

    def on(self, event_type: str, handler: Callable[[WebhookEvent], Any] | None = None):
        """Register a handler for a specific event type.

        Can be used as a direct call or as a decorator::

            # Direct call
            receiver.on("order.created", my_handler)

            # Decorator
            @receiver.on("order.created")
            def my_handler(event):
                ...

        Multiple handlers can be registered for the same event type.
        """
        if handler is not None:
            self._handlers[event_type].append(handler)
            return

        # Used as decorator
        def decorator(fn):
            self._handlers[event_type].append(fn)
            return fn

        return decorator

    def off(self, event_type: str, handler: Callable | None = None) -> None:
        """Remove handler(s) for a specific event type.

        If handler is provided, removes that specific handler.
        If handler is None, removes all handlers for the event type.
        """
        if handler is None:
            self._handlers.pop(event_type, None)
        elif event_type in self._handlers:
            try:
                self._handlers[event_type].remove(handler)
            except ValueError:
                pass

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

        If a handler raises an exception, the error is captured (via the
        on_error callback or a logged warning) and remaining handlers
        continue to execute.
        """
        results = []
        for handler in self._handlers.get(event.type, []):
            try:
                results.append(handler(event))
            except Exception as exc:
                self._handle_dispatch_error(exc, event, handler)
        for handler in self._handlers.get("*", []):
            try:
                results.append(handler(event))
            except Exception as exc:
                self._handle_dispatch_error(exc, event, handler)
        return results

    async def dispatch_async(self, event: WebhookEvent) -> list[Any]:
        """Route an event to all registered handlers, awaiting async ones.

        Works with both sync and async handlers. Async handlers are awaited,
        sync handlers are called normally.
        """
        results = []
        all_handlers = list(self._handlers.get(event.type, [])) + list(self._handlers.get("*", []))
        for handler in all_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    results.append(await handler(event))
                else:
                    results.append(handler(event))
            except Exception as exc:
                self._handle_dispatch_error(exc, event, handler)
        return results

    def process(self, payload: bytes, headers: dict[str, str]) -> WebhookEvent:
        """Verify, parse, and dispatch a webhook in one step.

        Combines receive() and dispatch().
        """
        event = self.receive(payload, headers)
        self.dispatch(event)
        return event

    async def process_async(self, payload: bytes, headers: dict[str, str]) -> WebhookEvent:
        """Verify, parse, and dispatch a webhook asynchronously.

        Combines receive() and dispatch_async().
        """
        event = self.receive(payload, headers)
        await self.dispatch_async(event)
        return event

    def _handle_dispatch_error(self, exc: Exception, event: WebhookEvent, handler: Callable) -> None:
        """Handle an error raised by a handler during dispatch."""
        if self._on_error:
            self._on_error(exc, event, handler)
        else:
            logger.warning(
                "Handler %r raised %s for event %r: %s",
                handler.__name__ if hasattr(handler, "__name__") else handler,
                type(exc).__name__,
                event.type,
                exc,
            )
