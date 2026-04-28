# webhookkit

Framework-agnostic webhook toolkit for Python. Send, receive, verify, and retry webhooks with ease.

## Features

- **Zero dependencies** — stdlib only for core functionality
- **Send webhooks** — sync (urllib) and async (httpx) delivery with automatic retries
- **Receive webhooks** — parse, verify, and dispatch incoming events
- **Signature verification** — built-in support for Stripe, GitHub, Shopify, Slack, and custom HMAC
- **Retry logic** — exponential backoff with jitter, configurable retry policies
- **Framework agnostic** — works with Django, Flask, FastAPI, or plain Python

## Installation

```bash
pip install webhookkit
```

With async support:
```bash
pip install webhookkit[async]
```

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

@app.post("/webhook")
def handle_webhook(request):
    event = receiver.receive(request.body, dict(request.headers))
    print(f"Received {event.type}: {event.payload}")
```

### Event Dispatching

```python
from webhookkit import WebhookReceiver, GitHubVerifier

receiver = WebhookReceiver(verifier=GitHubVerifier("your_secret"))

@receiver.on("push")
def handle_push(event):
    print(f"Push to {event.payload.get('ref')}")

@receiver.on("*")
def log_all(event):
    print(f"Event: {event.type}")

# In your endpoint handler:
receiver.process(request_body, request_headers)
```

### Verifying Signatures Directly

```python
from webhookkit import StripeVerifier, GitHubVerifier, ShopifyVerifier, SlackVerifier, HMACVerifier

# Stripe
verifier = StripeVerifier("whsec_...", tolerance=300)
is_valid = verifier.verify(payload_bytes, headers)

# GitHub
verifier = GitHubVerifier("secret")
verifier.verify_or_raise(payload_bytes, headers)  # raises on failure

# Custom HMAC
verifier = HMACVerifier("secret", header="X-My-Signature", algorithm="sha256", encoding="hex")
```

### Async Sending

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

## Supported Providers

| Provider | Verifier | Signer Scheme |
|----------|----------|---------------|
| Stripe | `StripeVerifier` | `"stripe"` |
| GitHub | `GitHubVerifier` | `"github"` |
| Shopify | `ShopifyVerifier` | `"shopify"` |
| Slack | `SlackVerifier` | `"slack"` |
| Custom HMAC | `HMACVerifier` | `"standard"` |

## API Reference

### Models

- `WebhookEvent(type, payload, id, timestamp, metadata)` — Represents a webhook event
- `RetryPolicy(max_retries, backoff, initial_delay, max_delay, jitter)` — Retry configuration
- `DeliveryResult` — Result of a delivery attempt (with `.success`, `.total_attempts`)

### Exceptions

- `SignatureVerificationError` — HMAC signature mismatch
- `TimestampVerificationError` — Timestamp outside tolerance window
- `DeliveryError` — All delivery attempts failed
- `PayloadError` — Invalid or unparseable payload

## License

MIT
