"""Approved source adapters: exactly OpenAlex, Crossref, arXiv, DataCite, Zenodo."""

from __future__ import annotations

from papersonar.sources.arxiv import ArxivAdapter
from papersonar.sources.base import BaseAdapter, FetchWindow, ParsedPage, SourceRecord
from papersonar.sources.crossref import CrossrefAdapter
from papersonar.sources.datacite import DataciteAdapter
from papersonar.sources.openalex import OpenAlexAdapter
from papersonar.sources.zenodo import ZenodoAdapter

ADAPTERS: dict[str, type[BaseAdapter]] = {
    OpenAlexAdapter.name: OpenAlexAdapter,
    CrossrefAdapter.name: CrossrefAdapter,
    ArxivAdapter.name: ArxivAdapter,
    DataciteAdapter.name: DataciteAdapter,
    ZenodoAdapter.name: ZenodoAdapter,
}

SOURCE_NAMES = tuple(ADAPTERS.keys())

__all__ = [
    "ADAPTERS",
    "SOURCE_NAMES",
    "ArxivAdapter",
    "BaseAdapter",
    "CrossrefAdapter",
    "DataciteAdapter",
    "FetchWindow",
    "OpenAlexAdapter",
    "ParsedPage",
    "SourceRecord",
    "ZenodoAdapter",
]
