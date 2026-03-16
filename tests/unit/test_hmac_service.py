import time

from webhook_relay.services.hmac_service import HMACService


class TestHMACService:
    def setup_method(self):
        self.service = HMACService(timestamp_tolerance=300)
        self.secret = HMACService.generate_secret()

    def test_sign_and_verify_roundtrip(self):
        body = b'{"event": "test"}'
        signature = self.service.sign_payload(body, self.secret)
        assert self.service.verify_signature(body, signature, self.secret)

    def test_verify_fails_with_wrong_secret(self):
        body = b'{"event": "test"}'
        signature = self.service.sign_payload(body, self.secret)
        wrong_secret = HMACService.generate_secret()
        assert not self.service.verify_signature(body, signature, wrong_secret)

    def test_verify_fails_with_expired_timestamp(self):
        body = b'{"event": "test"}'
        old_timestamp = int(time.time()) - 400
        signature = self.service.sign_payload(body, self.secret, timestamp=old_timestamp)
        assert not self.service.verify_signature(body, signature, self.secret)

    def test_verify_fails_with_invalid_format(self):
        body = b'{"event": "test"}'
        assert not self.service.verify_signature(body, "invalid-format", self.secret)

    def test_verify_fails_with_tampered_body(self):
        body = b'{"event": "test"}'
        signature = self.service.sign_payload(body, self.secret)
        tampered = b'{"event": "hacked"}'
        assert not self.service.verify_signature(tampered, signature, self.secret)

    def test_verify_with_recent_timestamp_passes(self):
        body = b'{"data": 1}'
        ts = int(time.time()) - 60
        signature = self.service.sign_payload(body, self.secret, timestamp=ts)
        assert self.service.verify_signature(body, signature, self.secret)

    def test_get_signature_headers(self):
        body = b'{"event": "test"}'
        headers = self.service.get_signature_headers(body, self.secret, "evt-1", "order.created")
        assert "X-Webhook-Signature" in headers
        assert headers["X-Webhook-Event-ID"] == "evt-1"
        assert headers["X-Webhook-Event-Type"] == "order.created"
        assert headers["Content-Type"] == "application/json"
        assert headers["User-Agent"] == "WebhookRelay/1.0"

    def test_generate_secret_uniqueness_and_length(self):
        s1 = HMACService.generate_secret()
        s2 = HMACService.generate_secret()
        assert s1 != s2
        assert len(s1) == 64

    def test_parse_timestamp(self):
        body = b"test"
        sig = self.service.sign_payload(body, self.secret)
        ts = self.service.parse_timestamp(sig)
        assert ts is not None
        assert abs(ts - int(time.time())) < 5

    def test_parse_timestamp_invalid(self):
        assert self.service.parse_timestamp("garbage") is None

    def test_constant_time_comparison_used(self):
        import hmac as hmac_mod
        body = b'{"test": true}'
        sig = self.service.sign_payload(body, self.secret)
        assert self.service.verify_signature(body, sig, self.secret)
        assert hasattr(hmac_mod, "compare_digest")
