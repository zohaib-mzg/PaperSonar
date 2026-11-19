"""PaperSonar extraction package (strict ELT).

Python's only job here is to fetch source records, serialise each raw object
unchanged as one JSON line, gzip the NDJSON file, and hand it to the runner for
upload. No cleaning, deduplication, categorisation, or key assignment is
performed in Python.
"""

from extract.registry import ADAPTERS, build_adapter

__all__ = ["ADAPTERS", "build_adapter"]
