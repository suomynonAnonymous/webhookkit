# webhookkit

Framework-agnostic webhook toolkit for Python. Send, receive, verify, and retry webhooks with ease.

## Features

- **Zero dependencies** — stdlib only for core functionality
- **Send webhooks** — sync (urllib) and async (httpx) delivery with automatic retries
- **Receive webhooks** — parse, verify, and dispatch incoming events
- **Signature verification** — built-in support for Stripe, GitHub, Shopify, Slack, and custom HMAC
- **Retry logic** — exponential backoff with jitter, configurable retry policies
- **Fully extensible** — create custom verifiers, senders, and receivers by subclassing
- **Framework agnostic** — works with Django, Flask, FastAPI, or plain Python

## Installation

```bash
pip install webhookkit
```

With async support (installs `httpx`):

```bash
pip install webhookkit[async]
```

---

## Quick Start

### Sending Webhooks

```python
from webhookkit import WebhookSender, RetryPolicy

sender = WebhookSender(
    signing_secret="whsec_your_secret",
    scheme="standard",
    retry_policy=RetryPolicy(max_retries=3),
)

result = sender.send(
    url="https://example.com/webhook",
    event_type="order.created",
    payload={"order_id": 123, "total": 49.99},
)
print(f"Delivered in {result.total_attempts} attempt(s)")
```

### Receiving & Verifying Webhooks

```python
from webhookkit import WebhookReceiver, StripeVerifier

receiver = WebhookReceiver(verifier=StripeVerifier("whsec_your_secret"))

# In your endpoint handler:
event = receiver.receive(request.body, dict(request.headers))
print(f"Received {event.type}: {event.payload}")
```

### Event Dispatching

Register handlers for specific event types and let the receiver route events automatically:

```python
from webhookkit import WebhookReceiver, GitHubVerifier

receiver = WebhookReceiver(verifier=GitHubVerifier("your_secret"))

# Register handlers
receiver.on("push", lambda event: print(f"Push to {event.payload.get('ref')}"))
receiver.on("pull_request", lambda event: handle_pr(event))
receiver.on("*", lambda event: log_event(event))  # wildcard — catches all events

# process() = receive + verify + dispatch, all in one call
event = receiver.process(request_body, request_headers)
```

---

## Using Built-in Verifiers

Each verifier matches the signature scheme of a specific webhook provider. Pass `payload` as `bytes` and `headers` as a `dict[str, str]`.

### Stripe

```python
from webhookkit import StripeVerifier

verifier = StripeVerifier("whsec_your_stripe_secret", tolerance=300)

# Returns True/False
is_valid = verifier.verify(payload_bytes, headers)

# Or raises SignatureVerificationError / TimestampVerificationError
verifier.verify_or_raise(payload_bytes, headers)
```

- **Header:** `Stripe-Signature: t=1234567890,v1=hmac_hex`
- **Signs:** `{timestamp}.{payload}` with HMAC-SHA256
- **Tolerance:** Rejects requests older than `tolerance` seconds (default 300s / 5 min)

### GitHub

```python
from webhookkit import GitHubVerifier

verifier = GitHubVerifier("your_github_webhook_secret")
verifier.verify_or_raise(payload_bytes, {"X-Hub-Signature-256": "sha256=abc..."})
```

- **Header:** `X-Hub-Signature-256: sha256=hmac_hex`
- **Signs:** raw payload with HMAC-SHA256

### Shopify

```python
from webhookkit import ShopifyVerifier

verifier = ShopifyVerifier("your_shopify_secret")
is_valid = verifier.verify(payload_bytes, {"X-Shopify-Hmac-SHA256": "base64hmac"})
```

- **Header:** `X-Shopify-Hmac-SHA256: base64_encoded_hmac`
- **Signs:** raw payload with HMAC-SHA256, base64-encoded

### Slack

```python
from webhookkit import SlackVerifier

verifier = SlackVerifier("your_slack_signing_secret", tolerance=300)
verifier.verify_or_raise(payload_bytes, {
    "X-Slack-Signature": "v0=hmac_hex",
    "X-Slack-Request-Timestamp": "1234567890",
})
```

- **Headers:** `X-Slack-Signature` + `X-Slack-Request-Timestamp`
- **Signs:** `v0:{timestamp}:{payload}` with HMAC-SHA256
- **Tolerance:** Rejects requests older than `tolerance` seconds

### Generic HMAC (any provider)

For any service that uses HMAC-based signatures (Twilio, SendGrid, your own app, etc.):

```python
from webhookkit import HMACVerifier

# Default: X-Webhook-Signature header, SHA256, hex encoding
verifier = HMACVerifier("your_secret")

# Fully customizable
verifier = HMACVerifier(
    secret="your_secret",
    header="X-My-Signature",    # which header to read
    algorithm="sha512",          # sha256, sha384, sha512
    encoding="base64",           # "hex" or "base64"
)
```

---

## Sending Webhooks

### Sync Sending (stdlib urllib)

```python
from webhookkit import WebhookSender, RetryPolicy, DeliveryError

sender = WebhookSender(
    signing_secret="your_secret",       # optional — signs payloads if provided
    scheme="standard",                   # "standard", "stripe", "github", "shopify", "slack"
    retry_policy=RetryPolicy(
        max_retries=3,
        initial_delay=1.0,
        max_delay=60.0,
        jitter=True,
    ),
    timeout=30,                          # seconds
    headers={"X-Custom-Header": "val"},  # extra headers on every request
)

try:
    result = sender.send(
        url="https://example.com/webhook",
        event_type="order.created",
        payload={"order_id": 123},
        idempotency_key="idem-abc-123",  # optional
    )
    print(f"Success: {result.success}, Attempts: {result.total_attempts}")
    for delivery in result.deliveries:
        print(f"  Attempt {delivery.attempt}: {delivery.status_code} ({delivery.duration_ms:.0f}ms)")
except DeliveryError as e:
    print(f"Failed after {e.attempts} attempts, last status: {e.status_code}")
```

**Security:** Only `http://` and `https://` URLs are allowed. Other schemes (e.g., `file://`, `ftp://`) are rejected to prevent SSRF. If you accept webhook URLs from users, you should additionally validate that they don't point to internal/private IP ranges.

**Headers sent automatically:**
- `Content-Type: application/json`
- `X-Webhook-ID: <uuid>`
- `X-Webhook-Timestamp: <unix_timestamp>`
- `X-Webhook-Event: <event_type>`
- Signature header (if `signing_secret` is set)
- `X-Webhook-Idempotency-Key` (if provided)

### Async Sending (requires httpx)

```python
import asyncio
from webhookkit import WebhookSender

sender = WebhookSender(signing_secret="secret")

async def main():
    result = await sender.send_async(
        url="https://example.com/webhook",
        event_type="user.created",
        payload={"user_id": 456},
    )
    print(f"Success: {result.success}")

asyncio.run(main())
```

### Retry Behavior

| Status Code | Behavior |
|-------------|----------|
| 2xx | Success — no retry |
| 4xx (except 408, 429) | Client error — no retry (won't change) |
| 408, 429 | Retryable (timeout / rate limited) |
| 5xx | Server error — retry |
| Connection error / timeout | Retry |

Retries use **exponential backoff**: delay = `initial_delay * 2^attempt`, capped at `max_delay`, with optional random jitter.

---

## Receiving Webhooks

### Basic Usage

```python
from webhookkit import WebhookReceiver

# Without verification (not recommended for production)
receiver = WebhookReceiver()

# With verification
receiver = WebhookReceiver(verifier=StripeVerifier("whsec_..."))
```

### Receive Only (verify + parse)

```python
event = receiver.receive(payload_bytes, headers_dict)
# event.id        -> "evt-abc-123"
# event.type      -> "order.created"
# event.timestamp -> 1714300000.0
# event.payload   -> {"order_id": 42}
# event.metadata  -> {}
```

### Register Event Handlers

```python
def handle_order(event):
    print(f"New order: {event.payload}")
    return "processed"

def handle_refund(event):
    issue_refund(event.payload["charge_id"])

def log_everything(event):
    logger.info(f"Webhook: {event.type}")

receiver.on("order.created", handle_order)
receiver.on("charge.refunded", handle_refund)
receiver.on("*", log_everything)  # wildcard handler
```

### Process (verify + parse + dispatch)

```python
# All-in-one: verify signature, parse payload, call matching handlers
event = receiver.process(payload_bytes, headers_dict)
```

### Dispatch Returns Handler Results

```python
receiver.on("test", lambda e: "ok")
receiver.on("test", lambda e: 42)

event = receiver.receive(b'{"type": "test"}', {})
results = receiver.dispatch(event)
# results == ["ok", 42]
```

---

## Framework Integration Examples

### Django

```python
# views.py
from django.http import HttpResponse, HttpResponseBadRequest
from webhookkit import WebhookReceiver, StripeVerifier, SignatureVerificationError

receiver = WebhookReceiver(verifier=StripeVerifier(settings.STRIPE_WEBHOOK_SECRET))
receiver.on("invoice.paid", lambda e: activate_subscription(e.payload["customer"]))
receiver.on("invoice.payment_failed", lambda e: notify_billing_failure(e.payload["customer"]))

def stripe_webhook(request):
    try:
        receiver.process(request.body, dict(request.headers))
        return HttpResponse(status=200)
    except SignatureVerificationError:
        return HttpResponseBadRequest("Invalid signature")
```

### Flask

```python
from flask import Flask, request, abort
from webhookkit import WebhookReceiver, GitHubVerifier, SignatureVerificationError

app = Flask(__name__)
receiver = WebhookReceiver(verifier=GitHubVerifier("your_secret"))
receiver.on("push", lambda e: trigger_deploy(e.payload["ref"]))

@app.post("/github-webhook")
def github_webhook():
    try:
        receiver.process(request.data, dict(request.headers))
        return "", 200
    except SignatureVerificationError:
        abort(403)
```

### FastAPI

```python
from fastapi import FastAPI, Request, HTTPException
from webhookkit import WebhookReceiver, ShopifyVerifier, SignatureVerificationError

app = FastAPI()
receiver = WebhookReceiver(verifier=ShopifyVerifier("your_secret"))
receiver.on("orders/create", lambda e: process_order(e.payload))

@app.post("/shopify-webhook")
async def shopify_webhook(request: Request):
    body = await request.body()
    try:
        receiver.process(body, dict(request.headers))
        return {"status": "ok"}
    except SignatureVerificationError:
        raise HTTPException(status_code=403, detail="Invalid signature")
```

---

## Creating Custom Verifiers

Subclass `BaseVerifier` to support any webhook provider with a non-standard signature scheme:

```python
from webhookkit.verifiers import BaseVerifier
from webhookkit.exceptions import SignatureVerificationError
import hashlib
import hmac

class TwilioVerifier(BaseVerifier):
    """Custom verifier for Twilio's request signing."""

    def __init__(self, auth_token: str):
        self.auth_token = auth_token

    def verify(self, payload: bytes, headers: dict[str, str]) -> bool:
        signature = headers.get("X-Twilio-Signature", "")
        if not signature:
            return False
        # Implement Twilio's specific verification logic here
        expected = hmac.new(
            self.auth_token.encode(), payload, hashlib.sha1
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

# Use it like any built-in verifier
receiver = WebhookReceiver(verifier=TwilioVerifier("your_twilio_auth_token"))
event = receiver.process(payload, headers)
```

The `verify_or_raise()` method is inherited automatically — it calls your `verify()` and raises `SignatureVerificationError` if it returns `False`.

---

## Creating Custom Senders

Extend `WebhookSender` to add custom behavior like logging, metrics, or different HTTP clients:

```python
from webhookkit.sender import WebhookSender
from webhookkit.models import DeliveryResult

class LoggingSender(WebhookSender):
    """Sender that logs every delivery attempt."""

    def send(self, url, event_type, payload, idempotency_key=None):
        print(f"Sending {event_type} to {url}")
        try:
            result = super().send(url, event_type, payload, idempotency_key)
            print(f"Delivered in {result.total_attempts} attempt(s)")
            return result
        except Exception as e:
            print(f"Delivery failed: {e}")
            raise

sender = LoggingSender(signing_secret="secret", scheme="github")
sender.send("https://example.com/hook", "deploy", {"sha": "abc123"})
```

---

## Creating Custom Receivers

Extend `WebhookReceiver` for custom parsing, logging, or middleware-like behavior:

```python
from webhookkit.receiver import WebhookReceiver
from webhookkit.models import WebhookEvent

class AuditReceiver(WebhookReceiver):
    """Receiver that logs all incoming events to a database."""

    def receive(self, payload, headers):
        event = super().receive(payload, headers)
        save_to_audit_log(event.type, event.payload, headers)
        return event

    def dispatch(self, event):
        results = super().dispatch(event)
        if not results:
            alert_unhandled_event(event.type)
        return results

receiver = AuditReceiver(verifier=StripeVerifier("whsec_..."))
receiver.on("payment.succeeded", handle_payment)
receiver.process(payload, headers)
```

---

## Supported Providers

| Provider | Verifier Class | Signer Scheme | Signature Header |
|----------|---------------|---------------|------------------|
| Stripe | `StripeVerifier` | `"stripe"` | `Stripe-Signature` |
| GitHub | `GitHubVerifier` | `"github"` | `X-Hub-Signature-256` |
| Shopify | `ShopifyVerifier` | `"shopify"` | `X-Shopify-Hmac-SHA256` |
| Slack | `SlackVerifier` | `"slack"` | `X-Slack-Signature` |
| Custom | `HMACVerifier` | `"standard"` | Configurable |

Any HMAC-based provider can be supported via `HMACVerifier` without subclassing. For providers with unique signing logic, subclass `BaseVerifier`.

---

## API Reference

### Models

| Class | Fields | Description |
|-------|--------|-------------|
| `WebhookEvent` | `id`, `type`, `timestamp`, `payload`, `metadata` | Represents a webhook event |
| `RetryPolicy` | `max_retries=3`, `backoff="exponential"`, `initial_delay=1.0`, `max_delay=60.0`, `jitter=True` | Retry configuration |
| `DeliveryResult` | `deliveries`, `success`, `total_attempts` | Aggregate delivery result |
| `WebhookDelivery` | `event`, `url`, `status_code`, `response_body`, `attempt`, `success`, `duration_ms` | Single delivery attempt |

### Exceptions

| Exception | Description |
|-----------|-------------|
| `WebhookError` | Base exception for all webhook errors |
| `SignatureVerificationError` | HMAC signature mismatch |
| `TimestampVerificationError` | Timestamp outside tolerance window |
| `DeliveryError` | All delivery attempts failed (has `.status_code`, `.attempts`) |
| `PayloadError` | Invalid or unparseable JSON payload |

### Sender

```python
WebhookSender(
    signing_secret=None,     # HMAC secret for signing payloads
    scheme="standard",       # "standard", "stripe", "github", "shopify", "slack"
    retry_policy=None,       # RetryPolicy instance (defaults to 3 retries)
    timeout=30,              # request timeout in seconds
    headers=None,            # extra headers dict added to every request
)

sender.send(url, event_type, payload, idempotency_key=None) -> DeliveryResult
sender.send_async(url, event_type, payload, idempotency_key=None) -> DeliveryResult
```

### Receiver

```python
WebhookReceiver(verifier=None)  # optional BaseVerifier subclass

receiver.on(event_type, handler)                       # register handler
receiver.receive(payload_bytes, headers) -> WebhookEvent  # verify + parse
receiver.dispatch(event) -> list                       # route to handlers
receiver.process(payload_bytes, headers) -> WebhookEvent  # all-in-one
```

### Verifiers

```python
# All verifiers share this interface:
verifier.verify(payload: bytes, headers: dict) -> bool
verifier.verify_or_raise(payload: bytes, headers: dict) -> None

# Built-in:
StripeVerifier(secret, tolerance=300)
GitHubVerifier(secret)
ShopifyVerifier(secret)
SlackVerifier(secret, tolerance=300)
HMACVerifier(secret, header="X-Webhook-Signature", algorithm="sha256", encoding="hex")
```

### Signing (for generating signatures)

```python
from webhookkit.signing import sign_payload, generate_signature_header

# Raw HMAC hex digest
signature = sign_payload(payload_bytes, secret, algorithm="sha256")

# Provider-formatted headers dict
headers = generate_signature_header(payload_bytes, secret, scheme="stripe", timestamp=None)
```

## License

MIT
