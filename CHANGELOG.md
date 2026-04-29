# Changelog

## 0.2.0 (2026-04-29)

### Added
- **Handler error isolation** — if a handler raises during `dispatch()`, remaining handlers still execute
- `on_error` callback parameter on `WebhookReceiver.__init__()` for custom error handling
- `off(event_type, handler=None)` method to unregister handlers
- Decorator-based handler registration: `@receiver.on("event")`
- `dispatch_async()` and `process_async()` for async handler support (mixed sync/async)
- `parse_retry_after()` — parse `Retry-After` header (integer seconds and HTTP-date)
- `retry_after` parameter on `calculate_delay()` — respects server-specified delays
- Retry-After header extraction in both sync and async sender retry loops
- Fresh timestamps and UUIDs on each retry attempt (no more stale signatures)

## 0.1.2 (2026-04-28)

### Security
- Pin all GitHub Actions to commit SHAs
- Whitelist HMAC algorithms to sha256/sha384/sha512 (reject md5/sha1)
- Validate URL scheme in sender (only http/https allowed)
- Sanitize URLs in error messages (strip query params and credentials)
- Add SECURITY.md, dependabot.yml, py.typed marker
- Replace personal email with GitHub noreply address

### Changed
- Bump pypa/gh-action-pypi-publish to v1.14.0
- Add top-level `permissions: contents: read` to CI workflow

## 0.1.1 (2026-04-28)

### Fixed
- Fix Python 3.9 compatibility (`from __future__ import annotations` in exceptions.py)
- Fix author display name on PyPI

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
