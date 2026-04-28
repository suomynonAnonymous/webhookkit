"""Tests for webhook sender."""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import pytest

from webhookkit.exceptions import DeliveryError
from webhookkit.models import RetryPolicy
from webhookkit.sender import WebhookSender


class _WebhookHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler for testing webhook delivery."""

    responses = []  # list of (status_code, body) tuples — pops from front

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        # Store request data for assertions
        self.server.last_request = {
            "headers": dict(self.headers),
            "body": body,
            "path": self.path,
        }
        if self.responses:
            status, resp_body = self.responses.pop(0)
        else:
            status, resp_body = 200, b"OK"
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(resp_body if isinstance(resp_body, bytes) else resp_body.encode())

    def log_message(self, format, *args):
        pass  # suppress logs


@pytest.fixture()
def webhook_server():
    """Start a local HTTP server for testing."""
    server = HTTPServer(("127.0.0.1", 0), _WebhookHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    yield server, f"http://127.0.0.1:{port}/webhook"
    server.shutdown()


class TestWebhookSender:
    def test_successful_delivery(self, webhook_server):
        server, url = webhook_server
        _WebhookHandler.responses = [(200, b"OK")]
        sender = WebhookSender()
        result = sender.send(url, "test.event", {"key": "value"})
        assert result.success is True
        assert result.total_attempts == 1
        assert result.deliveries[0].status_code == 200

    def test_request_headers_present(self, webhook_server):
        server, url = webhook_server
        _WebhookHandler.responses = [(200, b"OK")]
        sender = WebhookSender()
        sender.send(url, "order.created", {"id": 1})
        # urllib normalizes header capitalization, so check case-insensitively
        headers_lower = {k.lower(): v for k, v in server.last_request["headers"].items()}
        assert "x-webhook-id" in headers_lower
        assert "x-webhook-timestamp" in headers_lower
        assert headers_lower.get("x-webhook-event") == "order.created"
        assert headers_lower.get("content-type") == "application/json"

    def test_payload_is_event_dict(self, webhook_server):
        server, url = webhook_server
        _WebhookHandler.responses = [(200, b"OK")]
        sender = WebhookSender()
        sender.send(url, "test", {"data": 42})
        body = json.loads(server.last_request["body"])
        assert body["type"] == "test"
        assert body["payload"] == {"data": 42}
        assert "id" in body
        assert "timestamp" in body

    def test_signing(self, webhook_server):
        server, url = webhook_server
        _WebhookHandler.responses = [(200, b"OK")]
        sender = WebhookSender(signing_secret="mysecret", scheme="standard")
        sender.send(url, "test", {"a": 1})
        headers = server.last_request["headers"]
        assert "X-Webhook-Signature" in headers

    def test_idempotency_key(self, webhook_server):
        server, url = webhook_server
        _WebhookHandler.responses = [(200, b"OK")]
        sender = WebhookSender()
        sender.send(url, "test", {}, idempotency_key="idem-123")
        headers = server.last_request["headers"]
        assert headers.get("X-Webhook-Idempotency-Key") == "idem-123"

    def test_custom_default_headers(self, webhook_server):
        server, url = webhook_server
        _WebhookHandler.responses = [(200, b"OK")]
        sender = WebhookSender(headers={"X-Custom": "hello"})
        sender.send(url, "test", {})
        assert server.last_request["headers"].get("X-Custom") == "hello"

    def test_retry_on_server_error(self, webhook_server):
        server, url = webhook_server
        _WebhookHandler.responses = [(500, b"Error"), (200, b"OK")]
        policy = RetryPolicy(max_retries=3, initial_delay=0.01, jitter=False)
        sender = WebhookSender(retry_policy=policy)
        result = sender.send(url, "test", {})
        assert result.success is True
        assert result.total_attempts == 2

    def test_delivery_error_on_client_error(self, webhook_server):
        server, url = webhook_server
        _WebhookHandler.responses = [(400, b"Bad Request")]
        sender = WebhookSender()
        with pytest.raises(DeliveryError) as exc_info:
            sender.send(url, "test", {})
        assert exc_info.value.status_code == 400
        assert exc_info.value.attempts == 1

    def test_delivery_error_after_max_retries(self, webhook_server):
        server, url = webhook_server
        _WebhookHandler.responses = [(500, b"Err")] * 5
        policy = RetryPolicy(max_retries=2, initial_delay=0.01, jitter=False)
        sender = WebhookSender(retry_policy=policy)
        with pytest.raises(DeliveryError) as exc_info:
            sender.send(url, "test", {})
        assert exc_info.value.attempts == 3  # initial + 2 retries

    def test_connection_error(self):
        sender = WebhookSender(retry_policy=RetryPolicy(max_retries=0))
        with pytest.raises(DeliveryError):
            sender.send("http://127.0.0.1:1/nonexistent", "test", {})

    def test_rejects_non_http_url(self):
        sender = WebhookSender()
        with pytest.raises(ValueError, match="Only http and https"):
            sender.send("file:///etc/passwd", "test", {})

    def test_rejects_ftp_url(self):
        sender = WebhookSender()
        with pytest.raises(ValueError, match="Only http and https"):
            sender.send("ftp://example.com/data", "test", {})

    def test_error_message_strips_query_params(self, webhook_server):
        sender = WebhookSender(retry_policy=RetryPolicy(max_retries=0))
        with pytest.raises(DeliveryError) as exc_info:
            sender.send("http://127.0.0.1:1/hook?api_key=SECRET", "test", {})
        assert "SECRET" not in str(exc_info.value)
        assert "api_key" not in str(exc_info.value)

    def test_stripe_signing_scheme(self, webhook_server):
        server, url = webhook_server
        _WebhookHandler.responses = [(200, b"OK")]
        sender = WebhookSender(signing_secret="whsec_test", scheme="stripe")
        sender.send(url, "test", {})
        headers = server.last_request["headers"]
        assert "Stripe-Signature" in headers


class TestWebhookSenderAsync:
    @pytest.mark.asyncio
    async def test_async_successful_delivery(self, webhook_server):
        server, url = webhook_server
        _WebhookHandler.responses = [(200, b"OK")]
        sender = WebhookSender()
        result = await sender.send_async(url, "test.event", {"key": "value"})
        assert result.success is True
        assert result.total_attempts == 1

    @pytest.mark.asyncio
    async def test_async_retry_on_server_error(self, webhook_server):
        server, url = webhook_server
        _WebhookHandler.responses = [(502, b"Bad Gateway"), (200, b"OK")]
        policy = RetryPolicy(max_retries=3, initial_delay=0.01, jitter=False)
        sender = WebhookSender(retry_policy=policy)
        result = await sender.send_async(url, "test", {})
        assert result.success is True
        assert result.total_attempts == 2

    @pytest.mark.asyncio
    async def test_async_delivery_error(self, webhook_server):
        server, url = webhook_server
        _WebhookHandler.responses = [(400, b"Bad")]
        sender = WebhookSender()
        with pytest.raises(DeliveryError):
            await sender.send_async(url, "test", {})
