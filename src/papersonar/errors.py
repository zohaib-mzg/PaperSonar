"""Shared exception types for PaperSonar Phase 2."""

from __future__ import annotations


class ConfigurationError(RuntimeError):
    """Invalid or missing runtime configuration. Fail closed, never fall back."""


class IngestionError(RuntimeError):
    """A pipeline stage failed in a way that is not classified as retryable."""


class RetryableError(IngestionError):
    """Transient failure (network, 429, temporary 5xx). Safe to retry with backoff."""


class PermanentError(IngestionError):
    """Non-retryable failure (invalid parameters, permanent 4xx, schema mismatch)."""


class CheckpointError(IngestionError):
    """Checkpoint/state persistence failed; the watermark must not advance."""
