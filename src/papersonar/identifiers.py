"""Identifier normalization and content hashing.

Normalization is for comparison and canonical keys only; original source values
are always preserved by the caller (staging keeps raw fields).
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata

_WS_RE = re.compile(r"\s+")

# Common DOI URL/prefix forms. Loop-stripped so nested forms like
# "doi:https://doi.org/10.x/y" collapse fully.
_DOI_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
    "https://www.doi.org/",
    "http://www.doi.org/",
    "doi.org/",
    "dx.doi.org/",
    "doi:",
    "DOI:",
)

# Trailing punctuation that document text commonly leaves attached to a DOI.
_TRAILING_PUNCT = ".,;:)]}>'\""


def normalize_doi(raw: str | None) -> str | None:
    """Normalize a DOI for comparison; return ``None`` when unusable.

    Trims whitespace, lowercases, removes DOI URL/prefix forms and trailing
    punctuation. A usable normalized DOI must start with the ``10.`` registrant
    prefix; anything else is treated as malformed and rejected (the caller keeps
    the original value and may quarantine the record).
    """
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    text = unicodedata.normalize("NFKC", text).strip().lower()
    changed = True
    while changed:
        changed = False
        for prefix in _DOI_PREFIXES:
            if text.startswith(prefix.lower()):
                text = text[len(prefix) :].strip()
                changed = True
    text = text.rstrip().rstrip(_TRAILING_PUNCT).rstrip()
    text = _WS_RE.sub("", text)
    if not text or not text.startswith("10."):
        return None
    return text


def normalize_title(raw: str | None) -> str | None:
    """Normalize a work title for comparison keys.

    NFKC-normalizes, casefolds and collapses internal whitespace. ``None`` for
    blank/missing input.
    """
    if raw is None:
        return None
    text = unicodedata.normalize("NFKC", raw).strip()
    if not text:
        return None
    return _WS_RE.sub(" ", text).casefold()


def sha256_hex(data: bytes) -> str:
    """SHA-256 hex digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def canonical_json_bytes(obj: object) -> bytes:
    """Deterministic JSON encoding used for normalized content hashes."""
    return json.dumps(
        obj,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def canonical_json_hash(obj: object) -> str:
    """SHA-256 of the canonical JSON encoding of ``obj``."""
    return sha256_hex(canonical_json_bytes(obj))
