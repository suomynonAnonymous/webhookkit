"""Tests for webhook data models."""

import time

from webhookkit.models import DeliveryResult, RetryPolicy, WebhookDelivery, WebhookEvent


class TestWebhookEvent:
    def test_create_event(self):
        event = WebhookEvent(type="order.created", payload={"order_id": 123})
        assert event.type == "order.created"
        assert event.payload == {"order_id": 123}
        assert event.id  # auto-generated UUID
        assert event.timestamp > 0
        assert event.metadata == {}

    def test_event_with_custom_fields(self):
        event = WebhookEvent(
            type="test",
            payload={"key": "value"},
            id="custom-id",
            timestamp=1000.0,
            metadata={"source": "test"},
        )
        assert event.id == "custom-id"
        assert event.timestamp == 1000.0
        assert event.metadata == {"source": "test"}

    def test_to_dict(self):
        event = WebhookEvent(
            type="test.event",
            payload={"data": True},
            id="evt-123",
            timestamp=1234567890.0,
            metadata={"env": "test"},
        )
        d = event.to_dict()
        assert d == {
            "id": "evt-123",
            "type": "test.event",
            "timestamp": 1234567890.0,
            "payload": {"data": True},
            "metadata": {"env": "test"},
        }

    def test_unique_ids(self):
        e1 = WebhookEvent(type="a", payload={})
        e2 = WebhookEvent(type="a", payload={})
        assert e1.id != e2.id

    def test_timestamp_is_recent(self):
        before = time.time()
        event = WebhookEvent(type="a", payload={})
        after = time.time()
        assert before <= event.timestamp <= after


class TestRetryPolicy:
    def test_defaults(self):
        policy = RetryPolicy()
        assert policy.max_retries == 3
        assert policy.backoff == "exponential"
        assert policy.initial_delay == 1.0
        assert policy.max_delay == 60.0
        assert policy.jitter is True

    def test_custom_values(self):
        policy = RetryPolicy(max_retries=5, backoff="fixed", initial_delay=2.0, max_delay=120.0, jitter=False)
        assert policy.max_retries == 5
        assert policy.backoff == "fixed"
        assert policy.initial_delay == 2.0
        assert policy.max_delay == 120.0
        assert policy.jitter is False


class TestWebhookDelivery:
    def test_defaults(self):
        event = WebhookEvent(type="test", payload={})
        delivery = WebhookDelivery(event=event, url="https://example.com/webhook")
        assert delivery.status_code is None
        assert delivery.response_body == ""
        assert delivery.attempt == 1
        assert delivery.success is False
        assert delivery.duration_ms == 0.0


class TestDeliveryResult:
    def test_empty_result(self):
        result = DeliveryResult()
        assert result.success is False
        assert result.total_attempts == 0

    def test_success_result(self):
        event = WebhookEvent(type="test", payload={})
        d1 = WebhookDelivery(event=event, url="https://example.com", success=False, attempt=1)
        d2 = WebhookDelivery(event=event, url="https://example.com", success=True, attempt=2)
        result = DeliveryResult(deliveries=[d1, d2])
        assert result.success is True
        assert result.total_attempts == 2

    def test_failure_result(self):
        event = WebhookEvent(type="test", payload={})
        d1 = WebhookDelivery(event=event, url="https://example.com", success=False)
        result = DeliveryResult(deliveries=[d1])
        assert result.success is False
        assert result.total_attempts == 1
