# Source and corpus plan

Design baseline checked on 25 October 2026. Source policies must be checked again before implementing ingestion.

## Primary scholarly metadata

OpenAlex supplies publication identities and metadata, primary and secondary topics, source venues, authorships, institutional affiliations, matched references, and observed citation and access values.

Candidate topic identifiers returned by the pilot lookup:

| ID | Label |
| --- | --- |
| `T10743` | Software Testing and Debugging Techniques |
| `T12423` | Software Reliability and Analysis Research |
| `T12479` | Web Application Security Vulnerabilities |

These are candidates. Inspect their descriptions, annual counts, work types, and coverage before freezing the corpus. The draft [configuration](../config/corpus.example.json) is not evidence that a full corpus has been collected.

## Corpus definition

The proposed baseline covers publication years 2016 through 2025. The 2026 segment is separate and incomplete. A work is eligible when any supplied topic matches an admitted topic ID and its year and type satisfy the frozen configuration. Retain all supplied topics for admitted works and union overlapping partitions by canonical work identity.

Target 30,000 to 60,000 works after profiling. Narrow the declared boundary when necessary rather than silently truncating the first relevance-ranked results. Preserve the corpus definition, raw pages, configuration hash, and mapping revision.

## Supporting sources

Use Crossref for exact normalized DOI reconciliation. Keep discrepancy evidence rather than automatically replacing OpenAlex dates. Crossref is not an independent citation ground truth because OpenAlex incorporates its records.

ROR enrichment is optional and starts from known ROR IDs. Missing enrichment does not block the core import. Institution names alone are not automatic identity matches.

## Acquisition and refresh

Plan cursor-paged extraction with a free OpenAlex key, supported page size of 100, bounded usage, and durable checkpoints. Redact secrets from request logs. Stop before the free allowance is exhausted. Paid created-date and updated-date sync filters are excluded from the baseline.

The first implementation will re-fetch a bounded corpus. A complete successful refresh can publish one observation day. Partial runs must not become the latest reporting snapshot. This is not a guaranteed provider change feed or an atomic point-in-time source export.

Citation history starts with local observation. Current topic assignments can change. Retain extraction windows and raw evidence so earlier reports remain reproducible.

## Documentation

- [OpenAlex API](https://help.openalex.org/api/)
- [OpenAlex pricing](https://help.openalex.org/access/pricing/)
- [OpenAlex filters](https://help.openalex.org/api/filtering/)
- [OpenAlex pagination](https://help.openalex.org/api/paging/)
- [OpenAlex topics](https://help.openalex.org/data/topics/)
- [OpenAlex citations](https://help.openalex.org/data/works/citations/)
- [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)
- [ROR data dump](https://ror.readme.io/docs/data-dump)
