from datetime import datetime, timezone

from webhook_relay.services.retry_service import ExponentialBackoffStrategy


class TestExponentialBackoff:
    def setup_method(self):
        self.strategy = ExponentialBackoffStrategy()

    def test_first_attempt_delay(self):
        delay = self.strategy.compute_delay(attempt_number=1, jitter_factor=0)
        assert delay == 30.0

    def test_second_attempt_delay(self):
        delay = self.strategy.compute_delay(attempt_number=2, jitter_factor=0)
        assert delay == 60.0

    def test_third_attempt_delay(self):
        delay = self.strategy.compute_delay(attempt_number=3, jitter_factor=0)
        assert delay == 120.0

    def test_delay_capped_at_max(self):
        delay = self.strategy.compute_delay(
            attempt_number=20, max_delay_seconds=3600, jitter_factor=0
        )
        assert delay == 3600.0

    def test_jitter_adds_randomness(self):
        delays = {
            self.strategy.compute_delay(attempt_number=1, jitter_factor=0.5)
            for _ in range(50)
        }
        assert len(delays) > 1

    def test_should_retry_on_500(self):
        should, override = self.strategy.should_retry(500, 1, 5)
        assert should is True
        assert override is None

    def test_should_retry_on_502(self):
        should, _ = self.strategy.should_retry(502, 1, 5)
        assert should is True

    def test_should_retry_on_503(self):
        should, _ = self.strategy.should_retry(503, 1, 5)
        assert should is True

    def test_should_retry_on_504(self):
        should, _ = self.strategy.should_retry(504, 1, 5)
        assert should is True

    def test_should_not_retry_on_400(self):
        should, _ = self.strategy.should_retry(400, 1, 5)
        assert should is False

    def test_should_not_retry_on_401(self):
        should, _ = self.strategy.should_retry(401, 1, 5)
        assert should is False

    def test_should_not_retry_on_403(self):
        should, _ = self.strategy.should_retry(403, 1, 5)
        assert should is False

    def test_should_not_retry_on_404(self):
        should, _ = self.strategy.should_retry(404, 1, 5)
        assert should is False

    def test_should_not_retry_on_410(self):
        should, _ = self.strategy.should_retry(410, 1, 5)
        assert should is False

    def test_should_retry_on_connection_error(self):
        should, _ = self.strategy.should_retry(None, 1, 5)
        assert should is True

    def test_should_not_retry_when_max_exceeded(self):
        should, _ = self.strategy.should_retry(500, 5, 5)
        assert should is False

    def test_429_respects_retry_after(self):
        should, override = self.strategy.should_retry(429, 1, 5, retry_after_header="120")
        assert should is True
        assert override == 120.0

    def test_429_without_retry_after(self):
        should, override = self.strategy.should_retry(429, 1, 5)
        assert should is True
        assert override is None

    def test_429_with_invalid_retry_after(self):
        should, override = self.strategy.should_retry(429, 1, 5, retry_after_header="invalid")
        assert should is True
        assert override is None

    def test_next_retry_at_returns_future(self):
        result = self.strategy.next_retry_at(attempt_number=1)
        assert result > datetime.now(timezone.utc)

    def test_next_retry_at_with_override(self):
        result = self.strategy.next_retry_at(attempt_number=1, delay_override=60.0)
        now = datetime.now(timezone.utc)
        diff = (result - now).total_seconds()
        assert 59 < diff < 62

    def test_other_4xx_does_not_retry(self):
        should, _ = self.strategy.should_retry(422, 1, 5)
        assert should is False

    def test_other_5xx_retries(self):
        should, _ = self.strategy.should_retry(599, 1, 5)
        assert should is True
