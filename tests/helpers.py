"""Shared test helpers: fake HTTP session serving fixture bytes."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def fixture_bytes(*parts: str) -> bytes:
    return (FIXTURES.joinpath(*parts)).read_bytes()


@dataclass
class FakeResponse:
    status_code: int = 200
    content: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)
    url: str = "https://fake.test/ok"


class FakeSession:
    """records requests and returns scripted responses.

    When the script is exhausted, ``terminal_response`` is returned (use an
    empty/complete page so pagination loops end deterministically).
    """

    def __init__(
        self, responses: list[FakeResponse] | FakeResponse, terminal_response: FakeResponse | None = None
    ) -> None:
        self.responses = [responses] if isinstance(responses, FakeResponse) else responses
        self.terminal_response = terminal_response
        self.calls: list[dict[str, Any]] = []
        self._index = 0

    def get(self, url: str, params=None, headers=None, timeout=None):  # noqa: ANN001
        self.calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        if self._index < len(self.responses):
            response = self.responses[self._index]
        elif self.terminal_response is not None:
            response = self.terminal_response
        else:
            response = self.responses[-1]
        self._index += 1
        return response
