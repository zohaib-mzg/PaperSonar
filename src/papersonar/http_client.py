"""HTTP client with bounded retries, exponential backoff + jitter, Retry-After
compliance and rate-limit pacing shared by all source adapters."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Any

import requests

from papersonar.errors import PermanentError, RetryableError

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes
    headers: dict[str, str]
    url: str


class HttpClient:
    """Rate-limited GET with retry classification. One instance per source."""

    def __init__(
        self,
        timeout_seconds: float,
        max_attempts: int,
        backoff_base_seconds: float,
        backoff_max_seconds: float,
        rate_delay_seconds: float,
        user_agent: str,
        sleep: Any = time.sleep,
        session: requests.Session | None = None,
    ) -> None:
        self._timeout = timeout_seconds
        self._max_attempts = max(1, max_attempts)
        self._backoff_base = backoff_base_seconds
        self._backoff_max = backoff_max_seconds
        self._rate_delay = rate_delay_seconds
        self._user_agent = user_agent
        self._sleep = sleep if sleep is not None else time.sleep
        self.retry_count = 0
        self._session = session or requests.Session()

    def get(
        self,
        url: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> HttpResponse:
        """GET with pacing and bounded retries. Raises on permanent failure."""
        last_error: Exception | None = None
        last_retry_after: float | None = None
        for attempt in range(self._max_attempts):
            if attempt > 0:
                delay = self._backoff_delay(attempt, last_retry_after)
                logger.warning(
                    "retrying GET attempt=%d/%d delay=%.1fs url=%s",
                    attempt + 1,
                    self._max_attempts,
                    delay,
                    url,
                )
                self._sleep(delay)
            else:
                if self._rate_delay > 0:
                    self._sleep(self._rate_delay)
            try:
                response = self._session.get(
                    url,
                    params=params,
                    headers={"User-Agent": self._user_agent, **(headers or {})},
                    timeout=self._timeout,
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_error = exc
                last_retry_after = None
                self.retry_count += 1
                continue

            if response.status_code in RETRYABLE_STATUS:
                last_error = RetryableError(f"HTTP {response.status_code} from {url}")
                last_retry_after = _retry_after(response.headers.get("Retry-After"))
                self.retry_count += 1
                continue
            if 400 <= response.status_code < 500:
                # Non-retryable client error (except 429 handled above).
                raise PermanentError(
                    f"HTTP {response.status_code} (permanent) from {url}"
                )
            if response.status_code >= 500:
                last_error = RetryableError(f"HTTP {response.status_code} from {url}")
                last_retry_after = None
                self.retry_count += 1
                continue
            return HttpResponse(
                status=response.status_code,
                body=response.content,
                headers=dict(response.headers),
                url=str(response.url),
            )
        raise RetryableError(f"GET failed after {self._max_attempts} attempts: {last_error}")

    def _backoff_delay(self, attempt: int, retry_after: float | None) -> float:
        if retry_after is not None:
            return max(0.0, retry_after)
        exponential = min(self._backoff_max, self._backoff_base * (2 ** (attempt - 1)))
        jittered = exponential * (0.5 + random.random())
        return min(self._backoff_max, jittered)


def _retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None
