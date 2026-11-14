"""Logging setup with secret redaction.

Every log line passes through a redacting formatter that replaces known secret
values and common credential patterns (API keys, Authorization headers, private
key PEM blocks) before output. Resumption tokens are not treated as secrets.
"""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import Iterable

_REDACTED = "***REDACTED***"

# Credential-shaped patterns. Deliberately specific: OAI-PMH resumption tokens
# and pagination cursors are NOT secret and must remain visible in logs.
_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+"),
    re.compile(
        r"(?i)\b(api[_-]?key|apikey|access[_-]?token|auth[_-]?token|authorization|"
        r"password|passwd|passphrase|private[_-]?key|bearer|secret)\b\s*[=:]\s*"
        r"[^\s,&\"'<>]+"
    ),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
)


def redact_text(text: str, secrets: Iterable[str] = ()) -> str:
    """Redact known secret values and credential-shaped patterns from text."""
    result = text
    for secret in secrets:
        if secret and len(secret) >= 4:
            result = result.replace(secret, _REDACTED)
    for pattern in _PATTERNS:
        result = pattern.sub(_REDACTED, result)
    return result


class RedactingFormatter(logging.Formatter):
    """Formatter that redacts secrets from the fully formatted line."""

    def __init__(self, fmt: str | None = None, secrets: Iterable[str] = ()) -> None:
        super().__init__(fmt)
        self._secrets = list(secrets)

    def format(self, record: logging.LogRecord) -> str:
        return redact_text(super().format(record), self._secrets)


def setup_logging(level: str = "INFO", secrets: Iterable[str] = ()) -> None:
    """Configure root logging with redaction. Safe to call more than once."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        RedactingFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            secrets=secrets,
        )
    )
    root.addHandler(handler)
