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
