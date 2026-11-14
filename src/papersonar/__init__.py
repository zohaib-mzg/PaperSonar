"""PaperSonar research intelligence warehouse.

Phase 2: five-source metadata ingestion, raw/staging/canonical pipeline and a
Snowflake dimensional warehouse. Production target is fixed to Snowflake;
deterministic tests may inject a mocked Snowflake adapter as a testing
technique, which is not an alternate deployment target.
"""

__version__ = "0.2.0"
