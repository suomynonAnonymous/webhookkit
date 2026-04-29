"""Tests for retry logic."""

from webhookkit.models import RetryPolicy
from webhookkit.retry import RETRYABLE_STATUS_CODES, calculate_delay, parse_retry_after, should_retry


class TestCalculateDelay:
    def test_exponential_backoff(self):
        policy = RetryPolicy(initial_delay=1.0, jitter=False)
        assert calculate_delay(0, policy) == 1.0
        assert calculate_delay(1, policy) == 2.0
        assert calculate_delay(2, policy) == 4.0
        assert calculate_delay(3, policy) == 8.0

    def test_max_delay_cap(self):
        policy = RetryPolicy(initial_delay=1.0, max_delay=5.0, jitter=False)
        assert calculate_delay(10, policy) == 5.0

    def test_fixed_backoff(self):
        policy = RetryPolicy(backoff="fixed", initial_delay=2.0, jitter=False)
        assert calculate_delay(0, policy) == 2.0
        assert calculate_delay(1, policy) == 2.0
        assert calculate_delay(5, policy) == 2.0

    def test_jitter_within_range(self):
        policy = RetryPolicy(initial_delay=1.0, jitter=True)
        for _ in range(100):
            delay = calculate_delay(2, policy)
            assert 0 <= delay <= 4.0  # 1.0 * 2^2 = 4.0

    def test_jitter_not_always_same(self):
        policy = RetryPolicy(initial_delay=1.0, jitter=True)
        delays = {calculate_delay(2, policy) for _ in range(50)}
        assert len(delays) > 1  # jitter should produce varied values

    def test_calculate_delay_with_retry_after(self):
        """retry_after should override the calculated backoff."""
        policy = RetryPolicy(initial_delay=1.0, jitter=False)
        # retry_after = 10 should be used instead of exponential backoff
        assert calculate_delay(0, policy, retry_after=10.0) == 10.0

    def test_retry_after_capped_at_max_delay(self):
        """retry_after should still be capped at max_delay."""
        policy = RetryPolicy(initial_delay=1.0, max_delay=5.0, jitter=False)
        assert calculate_delay(0, policy, retry_after=100.0) == 5.0

    def test_retry_after_zero_uses_backoff(self):
        """retry_after=0 should fall through to normal backoff."""
        policy = RetryPolicy(initial_delay=1.0, jitter=False)
        assert calculate_delay(0, policy, retry_after=0) == 1.0

    def test_retry_after_negative_uses_backoff(self):
        """Negative retry_after should fall through to normal backoff."""
        policy = RetryPolicy(initial_delay=1.0, jitter=False)
        assert calculate_delay(0, policy, retry_after=-5.0) == 1.0

    def test_retry_after_none_uses_backoff(self):
        """None retry_after should use normal backoff."""
        policy = RetryPolicy(initial_delay=1.0, jitter=False)
        assert calculate_delay(0, policy, retry_after=None) == 1.0


class TestParseRetryAfter:
    def test_integer_seconds(self):
        assert parse_retry_after("120") == 120.0

    def test_float_seconds(self):
        assert parse_retry_after("1.5") == 1.5

    def test_none_value(self):
        assert parse_retry_after(None) is None

    def test_empty_string(self):
        assert parse_retry_after("") is None

    def test_invalid_string(self):
        assert parse_retry_after("not-a-number-or-date") is None

    def test_http_date_format(self):
        """HTTP-date should be parsed (result depends on current time)."""
        import email.utils
        import time

        # Create a date 60 seconds in the future
        future = time.time() + 60
        date_str = email.utils.formatdate(future, usegmt=True)
        result = parse_retry_after(date_str)
        assert result is not None
        assert 50 <= result <= 70  # roughly 60 seconds


class TestShouldRetry:
    def test_success_no_retry(self):
        policy = RetryPolicy(max_retries=3)
        assert should_retry(200, 0, policy) is False
        assert should_retry(201, 0, policy) is False
        assert should_retry(204, 0, policy) is False

    def test_client_error_no_retry(self):
        policy = RetryPolicy(max_retries=3)
        assert should_retry(400, 0, policy) is False
        assert should_retry(401, 0, policy) is False
        assert should_retry(403, 0, policy) is False
        assert should_retry(404, 0, policy) is False
        assert should_retry(422, 0, policy) is False

    def test_server_error_retry(self):
        policy = RetryPolicy(max_retries=3)
        for code in [500, 502, 503, 504]:
            assert should_retry(code, 0, policy) is True

    def test_special_retryable_codes(self):
        policy = RetryPolicy(max_retries=3)
        assert should_retry(408, 0, policy) is True  # request timeout
        assert should_retry(429, 0, policy) is True  # rate limited

    def test_connection_error_retry(self):
        policy = RetryPolicy(max_retries=3)
        assert should_retry(None, 0, policy) is True

    def test_max_retries_exceeded(self):
        policy = RetryPolicy(max_retries=3)
        assert should_retry(500, 3, policy) is False
        assert should_retry(None, 3, policy) is False

    def test_retryable_status_codes_constant(self):
        assert 500 in RETRYABLE_STATUS_CODES
        assert 502 in RETRYABLE_STATUS_CODES
        assert 503 in RETRYABLE_STATUS_CODES
        assert 504 in RETRYABLE_STATUS_CODES
        assert 408 in RETRYABLE_STATUS_CODES
        assert 429 in RETRYABLE_STATUS_CODES
