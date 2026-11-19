"""Bounded-retry HTTP client shared by all source extractors.

Retry policy (docs/phase2/03_SOURCES_AND_EXTRACTION.md): bounded exponential
backoff with jitter for 429 and eligible 5xx responses, ``Retry-After`` support,
and no endless retry for permanent 4xx responses. Request metrics are logged
without secrets or payload bodies.

Download policy: ``timeout_seconds`` only bounds the gap between socket reads,
so a response that trickles in never trips it. The body is therefore streamed
and a *total* deadline (``total_timeout_seconds``, default 4 x timeout) is
enforced per attempt. A blown deadline or a dropped chunked body is retried like
any other transient network error.
"""

from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass
from typing import Any, Protocol

import requests

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_CHUNK_BYTES = 64 * 1024

# ChunkedEncodingError is raised when a body is cut mid-download; it is not a
# subclass of ConnectionError, so it must be listed explicitly.
_NETWORK_ERRORS = (
    requests.ConnectionError,
    requests.Timeout,
    requests.exceptions.ChunkedEncodingError,
)


class PermanentHttpError(RuntimeError):
    """A request that must not be retried (e.g. HTTP 404 or 422)."""


class RetryableHttpError(RuntimeError):
    """A request that exhausted its bounded retry budget."""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes
    headers: dict[str, str]
    url: str

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


class Http(Protocol):
    """Minimal HTTP surface required by extractors (easy to fake in tests)."""

    def get(
        self,
        url: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> HttpResponse: ...


class HttpClient:
    """One instance per source so pacing and retry metrics stay isolated."""

    def __init__(
        self,
        timeout_seconds: float = 60.0,
        max_attempts: int = 4,
        backoff_base_seconds: float = 2.0,
        backoff_max_seconds: float = 60.0,
        rate_delay_seconds: float = 0.0,
        user_agent: str = "PaperSonar/0.3 (research metadata extraction)",
        sleep: Any = time.sleep,
        session: requests.Session | None = None,
        total_timeout_seconds: float | None = None,
    ) -> None:
        self._timeout = timeout_seconds
        self._max_attempts = max(1, max_attempts)
        self._backoff_base = backoff_base_seconds
        self._backoff_max = backoff_max_seconds
        self._rate_delay = rate_delay_seconds
        self._user_agent = user_agent
        self._sleep = sleep if sleep is not None else time.sleep
        self._session = session or requests.Session()
        if total_timeout_seconds is None:
            self._total_timeout: float | None = timeout_seconds * 4
        elif total_timeout_seconds <= 0:
            self._total_timeout = None  # explicitly disabled
        else:
            self._total_timeout = float(total_timeout_seconds)
        self.retry_count = 0
        self.request_count = 0

    def get(
        self,
        url: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> HttpResponse:
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
            elif self._rate_delay > 0:
                self._sleep(self._rate_delay)

            self.request_count += 1
            started = time.monotonic()
            try:
                response = self._session.get(
                    url,
                    params=params,
                    headers={"User-Agent": self._user_agent, **(headers or {})},
                    timeout=self._timeout,
                    stream=True,
                )
                if response.status_code < 400:
                    body = self._read_body(response, started)
                else:
                    body = b""
                    _close(response)
            except _NETWORK_ERRORS as exc:
                last_error = exc
                last_retry_after = None
                self.retry_count += 1
                logger.warning(
                    "GET network error after %.1fs: %s: %s url=%s",
                    time.monotonic() - started,
                    type(exc).__name__,
                    exc,
                    url,
                )
                continue

            if response.status_code in RETRYABLE_STATUS:
                last_error = RetryableHttpError(f"HTTP {response.status_code} from {url}")
                last_retry_after = _retry_after(response.headers.get("Retry-After"))
                self.retry_count += 1
                continue
            if 400 <= response.status_code < 500:
                raise PermanentHttpError(f"HTTP {response.status_code} (permanent) from {url}")
            if response.status_code >= 500:
                last_error = RetryableHttpError(f"HTTP {response.status_code} from {url}")
                last_retry_after = None
                self.retry_count += 1
                continue
            # url is the base URL only: query params may hold a contact email.
            logger.info(
                "GET status=%d bytes=%d elapsed=%.1fs url=%s",
                response.status_code,
                len(body),
                time.monotonic() - started,
                url,
            )
            return HttpResponse(
                status=response.status_code,
                body=body,
                headers=dict(response.headers),
                url=str(response.url),
            )
        raise RetryableHttpError(
            f"GET failed after {self._max_attempts} attempts: {last_error}"
        )

    def _read_body(self, response: Any, started: float) -> bytes:
        """Read the body in chunks, enforcing the total per-attempt deadline."""
        iter_content = getattr(response, "iter_content", None)
        if iter_content is None:  # minimal fakes used in tests
            return bytes(response.content)
        chunks: list[bytes] = []
        size = 0
        for chunk in iter_content(chunk_size=_CHUNK_BYTES):
            if chunk:
                chunks.append(chunk)
                size += len(chunk)
            if (
                self._total_timeout is not None
                and time.monotonic() - started > self._total_timeout
            ):
                _close(response)
                raise requests.Timeout(
                    f"total download deadline {self._total_timeout:.0f}s exceeded "
                    f"after {size} bytes"
                )
        return b"".join(chunks)

    def _backoff_delay(self, attempt: int, retry_after: float | None) -> float:
        if retry_after is not None:
            return max(0.0, min(retry_after, self._backoff_max))
        exponential = min(self._backoff_max, self._backoff_base * (2 ** (attempt - 1)))
        jittered = exponential * (0.5 + random.random())
        return min(self._backoff_max, jittered)


def _close(response: Any) -> None:
    close = getattr(response, "close", None)
    if callable(close):
        close()


def _retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None
