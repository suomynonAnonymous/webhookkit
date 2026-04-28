"""Webhook signature generation."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

ALLOWED_ALGORITHMS = frozenset({"sha256", "sha384", "sha512"})


def _get_hash_func(algorithm: str):
    """Return a hashlib constructor for the given algorithm, or raise ValueError."""
    if algorithm not in ALLOWED_ALGORITHMS:
        raise ValueError(f"Unsupported algorithm '{algorithm}'. Allowed: {', '.join(sorted(ALLOWED_ALGORITHMS))}")
    return getattr(hashlib, algorithm)


def sign_payload(payload: bytes, secret: str, algorithm: str = "sha256") -> str:
    """Create an HMAC signature for a payload.

    Returns the hex-encoded HMAC digest.
    """
    hash_func = _get_hash_func(algorithm)
    return hmac.new(secret.encode(), payload, hash_func).hexdigest()


def generate_signature_header(
    payload: bytes,
    secret: str,
    scheme: str = "standard",
    timestamp: float | None = None,
) -> dict[str, str]:
    """Generate webhook signature headers for a given scheme.

    Supported schemes: stripe, github, shopify, slack, standard.
    Returns a dict of headers to include in the webhook request.
    """
    if timestamp is None:
        timestamp = time.time()
    ts = str(int(timestamp))

    if scheme == "stripe":
        signed_payload = f"{ts}.".encode() + payload
        sig = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
        return {"Stripe-Signature": f"t={ts},v1={sig}"}

    if scheme == "github":
        sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return {"X-Hub-Signature-256": f"sha256={sig}"}

    if scheme == "shopify":
        sig = base64.b64encode(hmac.new(secret.encode(), payload, hashlib.sha256).digest()).decode()
        return {"X-Shopify-Hmac-SHA256": sig}

    if scheme == "slack":
        sig_basestring = f"v0:{ts}:".encode() + payload
        sig = hmac.new(secret.encode(), sig_basestring, hashlib.sha256).hexdigest()
        return {
            "X-Slack-Signature": f"v0={sig}",
            "X-Slack-Request-Timestamp": ts,
        }

    # standard scheme
    sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return {"X-Webhook-Signature": sig}
