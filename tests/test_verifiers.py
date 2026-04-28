"""Tests for webhook signature verifiers."""

import base64
import hashlib
import hmac
import time

import pytest

from webhookkit.exceptions import SignatureVerificationError, TimestampVerificationError
from webhookkit.signing import generate_signature_header
from webhookkit.verifiers import GitHubVerifier, HMACVerifier, ShopifyVerifier, SlackVerifier, StripeVerifier


class TestStripeVerifier:
    def setup_method(self):
        self.secret = "whsec_test_secret"
        self.verifier = StripeVerifier(self.secret, tolerance=300)
        self.payload = b'{"id": "evt_123", "type": "charge.succeeded"}'

    def test_valid_signature(self):
        headers = generate_signature_header(self.payload, self.secret, scheme="stripe")
        assert self.verifier.verify(self.payload, headers) is True

    def test_invalid_signature(self):
        headers = generate_signature_header(self.payload, "wrong-secret", scheme="stripe")
        assert self.verifier.verify(self.payload, headers) is False

    def test_tampered_payload(self):
        headers = generate_signature_header(self.payload, self.secret, scheme="stripe")
        assert self.verifier.verify(b"tampered", headers) is False

    def test_missing_header(self):
        assert self.verifier.verify(self.payload, {}) is False

    def test_expired_timestamp(self):
        old_ts = time.time() - 600
        headers = generate_signature_header(self.payload, self.secret, scheme="stripe", timestamp=old_ts)
        with pytest.raises(TimestampVerificationError):
            self.verifier.verify(self.payload, headers)

    def test_no_tolerance_check(self):
        verifier = StripeVerifier(self.secret, tolerance=0)
        old_ts = 1000000.0
        headers = generate_signature_header(self.payload, self.secret, scheme="stripe", timestamp=old_ts)
        assert verifier.verify(self.payload, headers) is True

    def test_verify_or_raise_valid(self):
        headers = generate_signature_header(self.payload, self.secret, scheme="stripe")
        self.verifier.verify_or_raise(self.payload, headers)  # should not raise

    def test_verify_or_raise_invalid(self):
        with pytest.raises(SignatureVerificationError):
            self.verifier.verify_or_raise(self.payload, {})

    def test_malformed_header(self):
        headers = {"Stripe-Signature": "garbage"}
        assert self.verifier.verify(self.payload, headers) is False


class TestGitHubVerifier:
    def setup_method(self):
        self.secret = "github-webhook-secret"
        self.verifier = GitHubVerifier(self.secret)
        self.payload = b'{"action": "opened", "number": 1}'

    def test_valid_signature(self):
        headers = generate_signature_header(self.payload, self.secret, scheme="github")
        assert self.verifier.verify(self.payload, headers) is True

    def test_invalid_signature(self):
        headers = generate_signature_header(self.payload, "wrong", scheme="github")
        assert self.verifier.verify(self.payload, headers) is False

    def test_missing_header(self):
        assert self.verifier.verify(self.payload, {}) is False

    def test_wrong_prefix(self):
        headers = {"X-Hub-Signature-256": "md5=abc123"}
        assert self.verifier.verify(self.payload, headers) is False

    def test_tampered_payload(self):
        headers = generate_signature_header(self.payload, self.secret, scheme="github")
        assert self.verifier.verify(b"different", headers) is False


class TestShopifyVerifier:
    def setup_method(self):
        self.secret = "shopify-secret"
        self.verifier = ShopifyVerifier(self.secret)
        self.payload = b'{"id": 123, "topic": "orders/create"}'

    def test_valid_signature(self):
        headers = generate_signature_header(self.payload, self.secret, scheme="shopify")
        assert self.verifier.verify(self.payload, headers) is True

    def test_invalid_signature(self):
        headers = generate_signature_header(self.payload, "wrong", scheme="shopify")
        assert self.verifier.verify(self.payload, headers) is False

    def test_missing_header(self):
        assert self.verifier.verify(self.payload, {}) is False

    def test_manual_base64_hmac(self):
        mac = hmac.new(self.secret.encode(), self.payload, hashlib.sha256).digest()
        sig = base64.b64encode(mac).decode()
        headers = {"X-Shopify-Hmac-SHA256": sig}
        assert self.verifier.verify(self.payload, headers) is True


class TestSlackVerifier:
    def setup_method(self):
        self.secret = "slack-signing-secret"
        self.verifier = SlackVerifier(self.secret, tolerance=300)
        self.payload = b"token=xoxb&team_id=T123&event=message"

    def test_valid_signature(self):
        headers = generate_signature_header(self.payload, self.secret, scheme="slack")
        assert self.verifier.verify(self.payload, headers) is True

    def test_invalid_signature(self):
        headers = generate_signature_header(self.payload, "wrong", scheme="slack")
        assert self.verifier.verify(self.payload, headers) is False

    def test_missing_headers(self):
        assert self.verifier.verify(self.payload, {}) is False
        assert self.verifier.verify(self.payload, {"X-Slack-Signature": "v0=abc"}) is False

    def test_expired_timestamp(self):
        old_ts = time.time() - 600
        headers = generate_signature_header(self.payload, self.secret, scheme="slack", timestamp=old_ts)
        with pytest.raises(TimestampVerificationError):
            self.verifier.verify(self.payload, headers)

    def test_wrong_prefix(self):
        ts = str(int(time.time()))
        headers = {"X-Slack-Signature": "v1=abc", "X-Slack-Request-Timestamp": ts}
        assert self.verifier.verify(self.payload, headers) is False

    def test_no_tolerance(self):
        verifier = SlackVerifier(self.secret, tolerance=0)
        old_ts = 1000000.0
        headers = generate_signature_header(self.payload, self.secret, scheme="slack", timestamp=old_ts)
        assert verifier.verify(self.payload, headers) is True


class TestHMACVerifier:
    def setup_method(self):
        self.secret = "custom-secret"
        self.verifier = HMACVerifier(self.secret)
        self.payload = b'{"event": "custom"}'

    def test_valid_signature(self):
        sig = hmac.new(self.secret.encode(), self.payload, hashlib.sha256).hexdigest()
        headers = {"X-Webhook-Signature": sig}
        assert self.verifier.verify(self.payload, headers) is True

    def test_invalid_signature(self):
        headers = {"X-Webhook-Signature": "invalid"}
        assert self.verifier.verify(self.payload, headers) is False

    def test_missing_header(self):
        assert self.verifier.verify(self.payload, {}) is False

    def test_custom_header_name(self):
        verifier = HMACVerifier(self.secret, header="X-Custom-Sig")
        sig = hmac.new(self.secret.encode(), self.payload, hashlib.sha256).hexdigest()
        headers = {"X-Custom-Sig": sig}
        assert verifier.verify(self.payload, headers) is True

    def test_base64_encoding(self):
        verifier = HMACVerifier(self.secret, encoding="base64")
        sig = base64.b64encode(hmac.new(self.secret.encode(), self.payload, hashlib.sha256).digest()).decode()
        headers = {"X-Webhook-Signature": sig}
        assert verifier.verify(self.payload, headers) is True

    def test_sha512_algorithm(self):
        verifier = HMACVerifier(self.secret, algorithm="sha512")
        sig = hmac.new(self.secret.encode(), self.payload, hashlib.sha512).hexdigest()
        headers = {"X-Webhook-Signature": sig}
        assert verifier.verify(self.payload, headers) is True
