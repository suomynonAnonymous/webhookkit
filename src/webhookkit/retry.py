"""Webhook retry logic with exponential backoff."""

from __future__ import annotations

import random

from .models import RetryPolicy

RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


def calculate_delay(attempt: int, policy: RetryPolicy) -> float:
    """Calculate the delay before the next retry attempt.

    Uses exponential backoff: initial_delay * 2^attempt, capped at max_delay.
    Optionally adds jitter (random value between 0 and the computed delay).
    """
    if policy.backoff == "exponential":
        delay = policy.initial_delay * (2**attempt)
    else:
        delay = policy.initial_delay

    delay = min(delay, policy.max_delay)

    if policy.jitter:
        delay = random.uniform(0, delay)  # noqa: S311

    return delay


def should_retry(status_code: int | None, attempt: int, policy: RetryPolicy) -> bool:
    """Determine whether a delivery should be retried.

    Retryable conditions:
    - status_code is None (connection error / timeout)
    - status_code in {408, 429, 500, 502, 503, 504}

    Not retryable:
    - 2xx (success)
    - Other 4xx (client error, won't change on retry)
    - Max retries exceeded
    """
    if attempt >= policy.max_retries:
        return False

    if status_code is None:
        return True

    return status_code in RETRYABLE_STATUS_CODES
