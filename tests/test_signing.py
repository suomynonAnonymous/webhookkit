"""Tests for webhook signature generation."""

import base64
import hashlib
import hmac

import pytest

from webhookkit.signing import generate_signature_header, sign_payload


class TestSignPayload:
    def test_sha256(self):
        payload = b'{"event": "test"}'
        secret = "mysecret"
        sig = sign_payload(payload, secret, algorithm="sha256")
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert sig == expected

    def test_sha512(self):
        payload = b"hello"
        secret = "key"
        sig = sign_payload(payload, secret, algorithm="sha512")
        expected = hmac.new(secret.encode(), payload, hashlib.sha512).hexdigest()
        assert sig == expected

    def test_default_algorithm_is_sha256(self):
        payload = b"test"
        secret = "s"
        sig = sign_payload(payload, secret)
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert sig == expected

    def test_disallowed_algorithm_raises(self):
        with pytest.raises(ValueError, match="Unsupported algorithm"):
            sign_payload(b"test", "secret", algorithm="md5")

    def test_sha1_disallowed(self):
        with pytest.raises(ValueError, match="Unsupported algorithm"):
            sign_payload(b"test", "secret", algorithm="sha1")


class TestGenerateSignatureHeader:
    def test_standard_scheme(self):
        payload = b'{"data": 1}'
        secret = "secret"
        headers = generate_signature_header(payload, secret, scheme="standard")
        assert "X-Webhook-Signature" in headers
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert headers["X-Webhook-Signature"] == expected

    def test_github_scheme(self):
        payload = b'{"ref": "main"}'
        secret = "gh-secret"
        headers = generate_signature_header(payload, secret, scheme="github")
        assert "X-Hub-Signature-256" in headers
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert headers["X-Hub-Signature-256"] == f"sha256={expected}"

    def test_shopify_scheme(self):
        payload = b'{"shop": "test"}'
        secret = "shopify-secret"
        headers = generate_signature_header(payload, secret, scheme="shopify")
        assert "X-Shopify-Hmac-SHA256" in headers
        expected = base64.b64encode(hmac.new(secret.encode(), payload, hashlib.sha256).digest()).decode()
        assert headers["X-Shopify-Hmac-SHA256"] == expected

    def test_stripe_scheme(self):
        payload = b'{"id": "evt_123"}'
        secret = "whsec_test"
        ts = 1700000000.0
        headers = generate_signature_header(payload, secret, scheme="stripe", timestamp=ts)
        assert "Stripe-Signature" in headers
        sig_header = headers["Stripe-Signature"]
        assert sig_header.startswith("t=1700000000,v1=")

    def test_slack_scheme(self):
        payload = b"token=abc&team_id=T123"
        secret = "slack-signing-secret"
        ts = 1700000000.0
        headers = generate_signature_header(payload, secret, scheme="slack", timestamp=ts)
        assert "X-Slack-Signature" in headers
        assert "X-Slack-Request-Timestamp" in headers
        assert headers["X-Slack-Request-Timestamp"] == "1700000000"
        assert headers["X-Slack-Signature"].startswith("v0=")

    def test_default_scheme_is_standard(self):
        payload = b"test"
        secret = "s"
        headers = generate_signature_header(payload, secret)
        assert "X-Webhook-Signature" in headers
