"""Extractor registry: maps the five approved sources to their adapters."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from extract.arxiv import ArxivExtractor
from extract.crossref import CrossrefExtractor
from extract.datacite import DataCiteExtractor
from extract.openalex import OpenAlexExtractor
from extract.zenodo import ZenodoExtractor


class UnsupportedSourceError(ValueError):
    """Raised when a source is not one of the five approved systems."""


ADAPTERS = {
    "openalex": OpenAlexExtractor,
    "crossref": CrossrefExtractor,
    "arxiv": ArxivExtractor,
    "datacite": DataCiteExtractor,
    "zenodo": ZenodoExtractor,
}


def build_adapter(
    source_name: str,
    config: Mapping[str, Any],
    *,
    openalex_api_key: str | None = None,
    crossref_contact_email: str | None = None,
) -> Any:
    """Build the extractor for ``source_name`` from its ``config/sources.yml`` block."""
    try:
        adapter_class = ADAPTERS[source_name]
    except KeyError as exc:
        raise UnsupportedSourceError(
            f"Unknown source {source_name!r}; approved: {', '.join(sorted(ADAPTERS))}"
        ) from exc
    if source_name == "openalex":
        return adapter_class(config, api_key=openalex_api_key)
    if source_name == "crossref":
        return adapter_class(config, contact_email=crossref_contact_email)
    return adapter_class(config)
