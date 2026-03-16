import hashlib
import hmac
import secrets
import time


class HMACService:
    SIGNATURE_HEADER = "X-Webhook-Signature"

    def __init__(self, timestamp_tolerance: int = 300):
        self._tolerance = timestamp_tolerance

    @staticmethod
    def generate_secret() -> str:
        return secrets.token_hex(32)

    def sign_payload(self, body: bytes, secret: str, timestamp: int | None = None) -> str:
        ts = timestamp or int(time.time())
        signed_content = f"{ts}.".encode() + body
        signature = hmac.new(
            key=secret.encode("utf-8"),
            msg=signed_content,
            digestmod=hashlib.sha256,
        ).hexdigest()
        return f"t={ts},v1={signature}"

    def verify_signature(self, body: bytes, signature_header: str, secret: str) -> bool:
        try:
            parts = dict(p.split("=", 1) for p in signature_header.split(","))
            timestamp = int(parts["t"])
            provided_sig = parts["v1"]
        except (KeyError, ValueError):
            return False

        age = abs(int(time.time()) - timestamp)
        if age > self._tolerance:
            return False

        signed_content = f"{timestamp}.".encode() + body
        expected_sig = hmac.new(
            key=secret.encode("utf-8"),
            msg=signed_content,
            digestmod=hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(provided_sig, expected_sig)

    def get_signature_headers(
        self, body: bytes, secret: str, event_id: str, event_type: str
    ) -> dict[str, str]:
        timestamp = int(time.time())
        return {
            self.SIGNATURE_HEADER: self.sign_payload(body, secret, timestamp),
            "X-Webhook-Event-ID": event_id,
            "X-Webhook-Event-Type": event_type,
            "X-Webhook-Timestamp": str(timestamp),
            "Content-Type": "application/json",
            "User-Agent": "WebhookRelay/1.0",
        }

    def parse_timestamp(self, signature_header: str) -> int | None:
        try:
            parts = dict(p.split("=", 1) for p in signature_header.split(","))
            return int(parts["t"])
        except (KeyError, ValueError):
            return None
