"""Webhook signature verifiers for various providers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

from .exceptions import SignatureVerificationError, TimestampVerificationError


class BaseVerifier:
    """Base class for webhook signature verifiers."""

    def verify(self, payload: bytes, headers: dict[str, str]) -> bool:
        """Verify webhook signature. Returns True if valid, False otherwise."""
        raise NotImplementedError

    def verify_or_raise(self, payload: bytes, headers: dict[str, str]) -> None:
        """Verify webhook signature. Raises on failure."""
        if not self.verify(payload, headers):
            raise SignatureVerificationError("Signature verification failed")


class StripeVerifier(BaseVerifier):
    """Verifies Stripe webhook signatures.

    Header: Stripe-Signature
    Format: t=timestamp,v1=hmac_hex
    Signs: {timestamp}.{payload}
    """

    def __init__(self, secret: str, tolerance: int = 300):
        self.secret = secret
        self.tolerance = tolerance

    def verify(self, payload: bytes, headers: dict[str, str]) -> bool:
        sig_header = headers.get("Stripe-Signature", "")
        if not sig_header:
            return False

        parts = {}
        for item in sig_header.split(","):
            key, _, value = item.partition("=")
            parts[key.strip()] = value.strip()

        timestamp = parts.get("t", "")
        signature = parts.get("v1", "")
        if not timestamp or not signature:
            return False

        if self.tolerance > 0:
            try:
                ts = int(timestamp)
            except ValueError:
                return False
            if abs(time.time() - ts) > self.tolerance:
                raise TimestampVerificationError(f"Timestamp difference exceeds tolerance of {self.tolerance}s")

        signed_payload = f"{timestamp}.".encode() + payload
        expected = hmac.new(self.secret.encode(), signed_payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


class GitHubVerifier(BaseVerifier):
    """Verifies GitHub webhook signatures.

    Header: X-Hub-Signature-256
    Format: sha256={hmac_hex}
    Signs: raw payload
    """

    def __init__(self, secret: str):
        self.secret = secret

    def verify(self, payload: bytes, headers: dict[str, str]) -> bool:
        sig_header = headers.get("X-Hub-Signature-256", "")
        if not sig_header:
            return False

        prefix = "sha256="
        if not sig_header.startswith(prefix):
            return False

        signature = sig_header[len(prefix) :]
        expected = hmac.new(self.secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


class ShopifyVerifier(BaseVerifier):
    """Verifies Shopify webhook signatures.

    Header: X-Shopify-Hmac-SHA256
    Format: base64-encoded HMAC
    Signs: raw payload
    """

    def __init__(self, secret: str):
        self.secret = secret

    def verify(self, payload: bytes, headers: dict[str, str]) -> bool:
        sig_header = headers.get("X-Shopify-Hmac-SHA256", "")
        if not sig_header:
            return False

        expected = base64.b64encode(hmac.new(self.secret.encode(), payload, hashlib.sha256).digest()).decode()
        return hmac.compare_digest(expected, sig_header)


class SlackVerifier(BaseVerifier):
    """Verifies Slack webhook signatures.

    Headers: X-Slack-Signature + X-Slack-Request-Timestamp
    Format: v0={hmac_hex}
    Signs: v0:{timestamp}:{payload}
    """

    def __init__(self, secret: str, tolerance: int = 300):
        self.secret = secret
        self.tolerance = tolerance

    def verify(self, payload: bytes, headers: dict[str, str]) -> bool:
        sig_header = headers.get("X-Slack-Signature", "")
        timestamp = headers.get("X-Slack-Request-Timestamp", "")
        if not sig_header or not timestamp:
            return False

        prefix = "v0="
        if not sig_header.startswith(prefix):
            return False

        signature = sig_header[len(prefix) :]

        if self.tolerance > 0:
            try:
                ts = int(timestamp)
            except ValueError:
                return False
            if abs(time.time() - ts) > self.tolerance:
                raise TimestampVerificationError(f"Timestamp difference exceeds tolerance of {self.tolerance}s")

        sig_basestring = f"v0:{timestamp}:".encode() + payload
        expected = hmac.new(self.secret.encode(), sig_basestring, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


class HMACVerifier(BaseVerifier):
    """Generic HMAC verifier for custom webhook providers.

    Configurable header name, algorithm, and encoding.
    """

    def __init__(
        self,
        secret: str,
        header: str = "X-Webhook-Signature",
        algorithm: str = "sha256",
        encoding: str = "hex",
    ):
        self.secret = secret
        self.header = header
        self.algorithm = algorithm
        self.encoding = encoding

    def verify(self, payload: bytes, headers: dict[str, str]) -> bool:
        sig_header = headers.get(self.header, "")
        if not sig_header:
            return False

        hash_func = getattr(hashlib, self.algorithm)
        mac = hmac.new(self.secret.encode(), payload, hash_func)

        if self.encoding == "base64":
            expected = base64.b64encode(mac.digest()).decode()
        else:
            expected = mac.hexdigest()

        return hmac.compare_digest(expected, sig_header)
