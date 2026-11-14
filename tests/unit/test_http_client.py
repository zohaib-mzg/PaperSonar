"""HTTP client retry/backoff/rate-limit behavior."""

import pytest

from papersonar.errors import PermanentError, RetryableError
from papersonar.http_client import HttpClient
from tests.helpers import FakeResponse, FakeSession


def make_client(session, max_attempts=3, base=1.0, cap=5.0):
    sleeps: list[float] = []
    client = HttpClient(
        timeout_seconds=5,
        max_attempts=max_attempts,
        backoff_base_seconds=base,
        backoff_max_seconds=cap,
        rate_delay_seconds=0.25,
        user_agent="PaperSonar-test/1.0",
        sleep=sleeps.append,
        session=session,
    )
    return client, sleeps


class TestRetryable:
    def test_429_with_retry_after(self):
        session = FakeSession(
            [
                FakeResponse(status_code=429, headers={"Retry-After": "7"}),
                FakeResponse(status_code=200, content=b"ok"),
            ]
        )
        client, sleeps = make_client(session)
        response = client.get("https://api.test/x")
        assert response.body == b"ok"
        assert sleeps[1] == 7.0  # Retry-After respected on the retry wait
        assert client.retry_count == 1

    def test_429_no_header_backoff_with_jitter(self):
        session = FakeSession(
            [FakeResponse(status_code=429), FakeResponse(status_code=200, content=b"ok")]
        )
        client, sleeps = make_client(session)
        assert client.get("https://api.test/x").body == b"ok"
        delay = sleeps[1]  # first sleep is the rate delay, second is the retry wait
        assert 0.5 <= delay <= 1.5  # base 1.0 with jitter in [0.5x, 1.5x]

    def test_500_retry_then_success(self):
        session = FakeSession(
            [FakeResponse(status_code=503), FakeResponse(status_code=200, content=b"ok")]
        )
        client, sleeps = make_client(session)
        assert client.get("https://api.test/x").body == b"ok"
        assert client.retry_count == 1

    def test_connection_error_retried(self):
        import requests as requests_lib

        class FlakySession:
            def __init__(self) -> None:
                self.calls = 0

            def get(self, url, params=None, headers=None, timeout=None):
                self.calls += 1
                if self.calls == 1:
                    raise requests_lib.ConnectionError("reset by peer")
                return FakeResponse(status_code=200, content=b"ok")

        client, sleeps = make_client(FlakySession())
        assert client.get("https://api.test/x").body == b"ok"
        assert client.retry_count == 1

    def test_exhaustion_raises_retryable(self):
        session = FakeSession([FakeResponse(status_code=429)])
        client, sleeps = make_client(session, max_attempts=3)
        with pytest.raises(RetryableError, match="after 3 attempts"):
            client.get("https://api.test/x")
        assert len(sleeps) == 3


class TestPermanent:
    def test_404_not_retried(self):
        session = FakeSession([FakeResponse(status_code=404, content=b"nope")])
        client, sleeps = make_client(session)
        with pytest.raises(PermanentError, match="404"):
            client.get("https://api.test/x")
        assert client.retry_count == 0
        assert sleeps == [0.25]  # initial rate delay only; no retry waits

    def test_401_not_retried(self):
        session = FakeSession([FakeResponse(status_code=401)])
        client, sleeps = make_client(session)
        with pytest.raises(PermanentError, match="401"):
            client.get("https://api.test/x")


class TestPacing:
    def test_rate_delay_before_first_request(self):
        session = FakeSession(FakeResponse(status_code=200, content=b"ok"))
        client, sleeps = make_client(session)
        client.get("https://api.test/x")
        assert sleeps == [0.25]
