"""Webhook sender with retry logic and signature support."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

from .exceptions import DeliveryError
from .models import DeliveryResult, RetryPolicy, WebhookDelivery, WebhookEvent
from .retry import calculate_delay, should_retry
from .signing import generate_signature_header


class WebhookSender:
    """Sends webhook events with automatic signing and retry logic.

    Uses stdlib urllib for sync delivery. If httpx is installed,
    async delivery is also available via send_async().
    """

    def __init__(
        self,
        signing_secret: str | None = None,
        scheme: str = "standard",
        retry_policy: RetryPolicy | None = None,
        timeout: int = 30,
        headers: dict[str, str] | None = None,
    ):
        self.signing_secret = signing_secret
        self.scheme = scheme
        self.retry_policy = retry_policy or RetryPolicy()
        self.timeout = timeout
        self.default_headers = headers or {}

    @staticmethod
    def _validate_url(url: str) -> None:
        """Reject non-HTTP(S) URL schemes to prevent SSRF."""
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Only http and https URLs are allowed, got: {parsed.scheme!r}")

    @staticmethod
    def _sanitize_url(url: str) -> str:
        """Strip query parameters and credentials from URL for safe use in error messages."""
        parsed = urllib.parse.urlparse(url)
        clean = parsed._replace(query="", fragment="")
        if parsed.username or parsed.password:
            clean = clean._replace(netloc=parsed.hostname or "")
            if parsed.port:
                clean = clean._replace(netloc=f"{parsed.hostname}:{parsed.port}")
        return urllib.parse.urlunparse(clean)

    def _build_request_headers(
        self, payload_bytes: bytes, event_type: str, idempotency_key: str | None = None
    ) -> dict[str, str]:
        """Build the full set of headers for a webhook request."""
        ts = str(int(time.time()))
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-ID": str(uuid.uuid4()),
            "X-Webhook-Timestamp": ts,
            "X-Webhook-Event": event_type,
            **self.default_headers,
        }

        if idempotency_key:
            headers["X-Webhook-Idempotency-Key"] = idempotency_key

        if self.signing_secret:
            sig_headers = generate_signature_header(
                payload_bytes, self.signing_secret, scheme=self.scheme, timestamp=float(ts)
            )
            headers.update(sig_headers)

        return headers

    def send(
        self,
        url: str,
        event_type: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> DeliveryResult:
        """Send a webhook event synchronously using urllib.

        Retries on 5xx/timeout according to the retry policy.
        Raises DeliveryError if all attempts fail.
        """
        self._validate_url(url)
        event = WebhookEvent(type=event_type, payload=payload)
        payload_bytes = json.dumps(event.to_dict()).encode()
        headers = self._build_request_headers(payload_bytes, event_type, idempotency_key)

        result = DeliveryResult()
        attempt = 0

        while True:
            delivery = WebhookDelivery(event=event, url=url, attempt=attempt + 1)
            start = time.monotonic()

            try:
                req = urllib.request.Request(url, data=payload_bytes, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    delivery.status_code = resp.status
                    delivery.response_body = resp.read().decode(errors="replace")
                    delivery.success = 200 <= resp.status < 300
            except urllib.error.HTTPError as e:
                delivery.status_code = e.code
                delivery.response_body = e.read().decode(errors="replace")
            except (urllib.error.URLError, TimeoutError, OSError):
                delivery.status_code = None

            delivery.duration_ms = (time.monotonic() - start) * 1000
            result.deliveries.append(delivery)

            if delivery.success:
                return result

            if not should_retry(delivery.status_code, attempt, self.retry_policy):
                break

            delay = calculate_delay(attempt, self.retry_policy)
            time.sleep(delay)
            attempt += 1

        raise DeliveryError(
            f"Webhook delivery to {self._sanitize_url(url)} failed after {result.total_attempts} attempt(s)",
            status_code=result.deliveries[-1].status_code,
            attempts=result.total_attempts,
        )

    async def send_async(
        self,
        url: str,
        event_type: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> DeliveryResult:
        """Send a webhook event asynchronously using httpx.

        Requires httpx to be installed: pip install webhookkit[async]
        """
        self._validate_url(url)
        try:
            import httpx
        except ImportError:
            raise ImportError("httpx is required for async sending: pip install webhookkit[async]") from None

        import asyncio

        event = WebhookEvent(type=event_type, payload=payload)
        payload_bytes = json.dumps(event.to_dict()).encode()
        headers = self._build_request_headers(payload_bytes, event_type, idempotency_key)

        result = DeliveryResult()
        attempt = 0

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            while True:
                delivery = WebhookDelivery(event=event, url=url, attempt=attempt + 1)
                start = time.monotonic()

                try:
                    resp = await client.post(url, content=payload_bytes, headers=headers)
                    delivery.status_code = resp.status_code
                    delivery.response_body = resp.text
                    delivery.success = 200 <= resp.status_code < 300
                except httpx.TimeoutException:
                    delivery.status_code = None
                except httpx.HTTPError:
                    delivery.status_code = None

                delivery.duration_ms = (time.monotonic() - start) * 1000
                result.deliveries.append(delivery)

                if delivery.success:
                    return result

                if not should_retry(delivery.status_code, attempt, self.retry_policy):
                    break

                delay = calculate_delay(attempt, self.retry_policy)
                await asyncio.sleep(delay)
                attempt += 1

        raise DeliveryError(
            f"Webhook delivery to {self._sanitize_url(url)} failed after {result.total_attempts} attempt(s)",
            status_code=result.deliveries[-1].status_code,
            attempts=result.total_attempts,
        )
