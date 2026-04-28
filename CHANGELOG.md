# Changelog

## 0.1.0 (2026-04-28)

### Added
- Initial release
- `WebhookSender` — sync + async webhook delivery with automatic retries
- `WebhookReceiver` — receive, verify, and dispatch webhook events
- Built-in signature verifiers: Stripe, GitHub, Shopify, Slack, custom HMAC
- Signature generation for all supported schemes
- Exponential backoff with jitter retry logic
- Zero runtime dependencies (stdlib only)
- Optional `httpx` support for async sending
