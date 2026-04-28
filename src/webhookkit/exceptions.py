"""Webhook exception classes."""

from __future__ import annotations


class WebhookError(Exception):
    """Base exception for all webhook errors."""


class SignatureVerificationError(WebhookError):
    """Raised when webhook signature verification fails."""


class TimestampVerificationError(WebhookError):
    """Raised when webhook timestamp is outside the tolerance window."""


class DeliveryError(WebhookError):
    """Raised when webhook delivery fails after all retry attempts."""

    def __init__(self, message: str, status_code: int | None = None, attempts: int = 0):
        super().__init__(message)
        self.status_code = status_code
        self.attempts = attempts


class PayloadError(WebhookError):
    """Raised when webhook payload is invalid or cannot be parsed."""
