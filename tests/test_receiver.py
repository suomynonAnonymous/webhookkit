"""Tests for webhook receiver."""

import json

import pytest

from webhookkit.exceptions import PayloadError, SignatureVerificationError
from webhookkit.receiver import WebhookReceiver
from webhookkit.signing import generate_signature_header
from webhookkit.verifiers import HMACVerifier


class TestWebhookReceiver:
    def test_receive_valid_payload(self):
        receiver = WebhookReceiver()
        payload = json.dumps({"id": "evt-1", "type": "order.created", "payload": {"order_id": 42}}).encode()
        event = receiver.receive(payload, {})
        assert event.type == "order.created"
        assert event.id == "evt-1"
        assert event.payload == {"order_id": 42}

    def test_receive_minimal_payload(self):
        receiver = WebhookReceiver()
        payload = json.dumps({"type": "ping"}).encode()
        event = receiver.receive(payload, {})
        assert event.type == "ping"
        assert event.id == ""

    def test_receive_non_standard_payload(self):
        """When the payload doesn't have the standard structure, the whole dict becomes the payload."""
        receiver = WebhookReceiver()
        payload = json.dumps({"action": "completed", "repo": "test"}).encode()
        event = receiver.receive(payload, {})
        assert event.payload == {"action": "completed", "repo": "test"}

    def test_receive_invalid_json(self):
        receiver = WebhookReceiver()
        with pytest.raises(PayloadError, match="Invalid JSON"):
            receiver.receive(b"not json", {})

    def test_receive_non_object_json(self):
        receiver = WebhookReceiver()
        with pytest.raises(PayloadError, match="must be a JSON object"):
            receiver.receive(b"[1, 2, 3]", {})

    def test_receive_with_verifier_valid(self):
        secret = "test-secret"
        verifier = HMACVerifier(secret)
        receiver = WebhookReceiver(verifier=verifier)
        payload = json.dumps({"type": "test"}).encode()
        headers = generate_signature_header(payload, secret, scheme="standard")
        event = receiver.receive(payload, headers)
        assert event.type == "test"

    def test_receive_with_verifier_invalid(self):
        verifier = HMACVerifier("correct-secret")
        receiver = WebhookReceiver(verifier=verifier)
        payload = json.dumps({"type": "test"}).encode()
        headers = generate_signature_header(payload, "wrong-secret", scheme="standard")
        with pytest.raises(SignatureVerificationError):
            receiver.receive(payload, headers)


class TestWebhookReceiverDispatch:
    def test_dispatch_to_handler(self):
        receiver = WebhookReceiver()
        results = []
        receiver.on("order.created", lambda e: results.append(e.type))
        payload = json.dumps({"type": "order.created", "payload": {}}).encode()
        event = receiver.receive(payload, {})
        receiver.dispatch(event)
        assert results == ["order.created"]

    def test_dispatch_multiple_handlers(self):
        receiver = WebhookReceiver()
        r1, r2 = [], []
        receiver.on("test", lambda e: r1.append(1))
        receiver.on("test", lambda e: r2.append(2))
        payload = json.dumps({"type": "test", "payload": {}}).encode()
        event = receiver.receive(payload, {})
        receiver.dispatch(event)
        assert r1 == [1]
        assert r2 == [2]

    def test_dispatch_wildcard_handler(self):
        receiver = WebhookReceiver()
        all_events = []
        receiver.on("*", lambda e: all_events.append(e.type))
        payload = json.dumps({"type": "any.event", "payload": {}}).encode()
        event = receiver.receive(payload, {})
        receiver.dispatch(event)
        assert all_events == ["any.event"]

    def test_dispatch_no_matching_handler(self):
        receiver = WebhookReceiver()
        receiver.on("other.event", lambda e: None)
        payload = json.dumps({"type": "test", "payload": {}}).encode()
        event = receiver.receive(payload, {})
        results = receiver.dispatch(event)
        assert results == []

    def test_dispatch_returns_handler_results(self):
        receiver = WebhookReceiver()
        receiver.on("test", lambda e: "handled")
        payload = json.dumps({"type": "test", "payload": {}}).encode()
        event = receiver.receive(payload, {})
        results = receiver.dispatch(event)
        assert results == ["handled"]

    def test_process_all_in_one(self):
        receiver = WebhookReceiver()
        handled = []
        receiver.on("ping", lambda e: handled.append(True))
        payload = json.dumps({"type": "ping", "payload": {}}).encode()
        event = receiver.process(payload, {})
        assert event.type == "ping"
        assert handled == [True]

    def test_process_with_verification(self):
        secret = "s3cr3t"
        verifier = HMACVerifier(secret)
        receiver = WebhookReceiver(verifier=verifier)
        handled = []
        receiver.on("test", lambda e: handled.append(True))
        payload = json.dumps({"type": "test", "payload": {}}).encode()
        headers = generate_signature_header(payload, secret, scheme="standard")
        event = receiver.process(payload, headers)
        assert event.type == "test"
        assert handled == [True]


class TestDecoratorRegistration:
    def test_decorator_registration(self):
        receiver = WebhookReceiver()

        @receiver.on("order.created")
        def handle_order(event):
            return "order_handled"

        payload = json.dumps({"type": "order.created", "payload": {}}).encode()
        event = receiver.receive(payload, {})
        results = receiver.dispatch(event)
        assert results == ["order_handled"]
        # Decorator should return the original function
        assert handle_order is not None
        assert callable(handle_order)

    def test_decorator_preserves_function(self):
        receiver = WebhookReceiver()

        @receiver.on("test")
        def my_handler(event):
            return "result"

        # The decorated function should still be callable directly
        assert my_handler.__name__ == "my_handler"


class TestHandlerErrorIsolation:
    def test_handler_error_isolation(self):
        """If one handler raises, others should still be called."""
        receiver = WebhookReceiver()
        results = []

        receiver.on("test", lambda e: results.append("first"))

        def bad_handler(e):
            raise ValueError("boom")

        receiver.on("test", bad_handler)
        receiver.on("test", lambda e: results.append("third"))

        payload = json.dumps({"type": "test", "payload": {}}).encode()
        event = receiver.receive(payload, {})
        receiver.dispatch(event)

        assert results == ["first", "third"]

    def test_on_error_callback(self):
        """Custom on_error callback should be invoked on handler errors."""
        errors = []

        def error_handler(exc, event, handler):
            errors.append((type(exc).__name__, event.type, handler.__name__))

        receiver = WebhookReceiver(on_error=error_handler)

        def bad_handler(event):
            raise RuntimeError("fail")

        receiver.on("test", bad_handler)

        payload = json.dumps({"type": "test", "payload": {}}).encode()
        event = receiver.receive(payload, {})
        receiver.dispatch(event)

        assert len(errors) == 1
        assert errors[0] == ("RuntimeError", "test", "bad_handler")

    def test_error_isolation_with_wildcard(self):
        """Errors in wildcard handlers shouldn't block other wildcard handlers."""
        receiver = WebhookReceiver()
        results = []

        def bad_wildcard(e):
            raise ValueError("oops")

        receiver.on("*", bad_wildcard)
        receiver.on("*", lambda e: results.append("wildcard_ok"))

        payload = json.dumps({"type": "test", "payload": {}}).encode()
        event = receiver.receive(payload, {})
        receiver.dispatch(event)

        assert results == ["wildcard_ok"]


class TestHandlerRemoval:
    def test_off_removes_handler(self):
        receiver = WebhookReceiver()
        results = []

        def handler_a(e):
            results.append("a")

        def handler_b(e):
            results.append("b")

        receiver.on("test", handler_a)
        receiver.on("test", handler_b)
        receiver.off("test", handler_a)

        payload = json.dumps({"type": "test", "payload": {}}).encode()
        event = receiver.receive(payload, {})
        receiver.dispatch(event)
        assert results == ["b"]

    def test_off_removes_all_handlers(self):
        receiver = WebhookReceiver()
        results = []
        receiver.on("test", lambda e: results.append("a"))
        receiver.on("test", lambda e: results.append("b"))
        receiver.off("test")

        payload = json.dumps({"type": "test", "payload": {}}).encode()
        event = receiver.receive(payload, {})
        receiver.dispatch(event)
        assert results == []

    def test_off_nonexistent_handler(self):
        """Removing a handler that doesn't exist should not raise."""
        receiver = WebhookReceiver()
        receiver.on("test", lambda e: None)
        receiver.off("test", lambda e: None)  # different lambda, no-op

    def test_off_nonexistent_event(self):
        """Removing handlers for an unregistered event should not raise."""
        receiver = WebhookReceiver()
        receiver.off("nonexistent")


class TestAsyncDispatch:
    @pytest.mark.asyncio
    async def test_async_dispatch(self):
        receiver = WebhookReceiver()

        async def async_handler(event):
            return f"async_{event.type}"

        receiver.on("test", async_handler)

        payload = json.dumps({"type": "test", "payload": {}}).encode()
        event = receiver.receive(payload, {})
        results = await receiver.dispatch_async(event)
        assert results == ["async_test"]

    @pytest.mark.asyncio
    async def test_mixed_sync_async_handlers(self):
        receiver = WebhookReceiver()

        def sync_handler(event):
            return "sync"

        async def async_handler(event):
            return "async"

        receiver.on("test", sync_handler)
        receiver.on("test", async_handler)

        payload = json.dumps({"type": "test", "payload": {}}).encode()
        event = receiver.receive(payload, {})
        results = await receiver.dispatch_async(event)
        assert results == ["sync", "async"]

    @pytest.mark.asyncio
    async def test_async_process(self):
        receiver = WebhookReceiver()
        handled = []

        async def handler(event):
            handled.append(event.type)

        receiver.on("ping", handler)

        payload = json.dumps({"type": "ping", "payload": {}}).encode()
        event = await receiver.process_async(payload, {})
        assert event.type == "ping"
        assert handled == ["ping"]

    @pytest.mark.asyncio
    async def test_async_error_isolation(self):
        """Errors in async dispatch should be isolated."""
        receiver = WebhookReceiver()
        results = []

        async def bad_handler(event):
            raise ValueError("async boom")

        async def good_handler(event):
            results.append("ok")

        receiver.on("test", bad_handler)
        receiver.on("test", good_handler)

        payload = json.dumps({"type": "test", "payload": {}}).encode()
        event = receiver.receive(payload, {})
        await receiver.dispatch_async(event)
        assert results == ["ok"]
