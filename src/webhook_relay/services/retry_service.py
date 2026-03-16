import random
from datetime import datetime, timedelta, timezone


class ExponentialBackoffStrategy:
    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
    PERMANENT_FAILURE_CODES = {400, 401, 403, 404, 410}

    def compute_delay(
        self,
        attempt_number: int,
        base: float = 2.0,
        initial_delay_seconds: float = 30.0,
        max_delay_seconds: int = 3600,
        jitter_factor: float = 0.25,
    ) -> float:
        raw_delay = min(
            initial_delay_seconds * (base ** (attempt_number - 1)),
            max_delay_seconds,
        )
        jitter = random.uniform(0, raw_delay * jitter_factor)
        return raw_delay + jitter

    def should_retry(
        self,
        http_status_code: int | None,
        attempt_count: int,
        max_retries: int,
        retry_after_header: str | None = None,
    ) -> tuple[bool, float | None]:
        if attempt_count >= max_retries:
            return False, None

        if http_status_code is None:
            return True, None

        if http_status_code in self.PERMANENT_FAILURE_CODES:
            return False, None

        if http_status_code in self.RETRYABLE_STATUS_CODES:
            delay_override = None
            if http_status_code == 429 and retry_after_header:
                try:
                    delay_override = float(retry_after_header)
                except ValueError:
                    pass
            return True, delay_override

        if 400 <= http_status_code < 500:
            return False, None

        return True, None

    def next_retry_at(
        self,
        attempt_number: int,
        backoff_base: float = 2.0,
        max_delay_seconds: int = 3600,
        delay_override: float | None = None,
    ) -> datetime:
        delay = delay_override or self.compute_delay(
            attempt_number=attempt_number,
            base=backoff_base,
            max_delay_seconds=max_delay_seconds,
        )
        return datetime.now(timezone.utc) + timedelta(seconds=delay)
