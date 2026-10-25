# Source pilot

These are actual source responses collected on 25 October 2026 to inspect fields and verify access. They are a small design pilot, not the final research corpus.

| File | Contents |
| --- | --- |
| [openalex_works_pilot.json](openalex_works_pilot.json) | 20 records from an OpenAlex search for `software testing`, restricted to publication year 2024. |
| [publication_sample.csv](publication_sample.csv) | Selected fields from the same 20 works. Citation and access values describe retrieval time. |
| [openalex_topics_pilot.json](openalex_topics_pilot.json) | A topic lookup used to identify candidate software-related topics. |
| [crossref_doi_pilot.json](crossref_doi_pilot.json) | One exact DOI lookup for a work in the pilot. |
| [retrieval_manifest.json](retrieval_manifest.json) | Retrieval URLs, UTC timestamps, and SHA256 hashes for the three JSON responses. |

## Interpretation

The works query is relevance-ranked and keyword-selected. It is unsuitable for estimating topic growth, global research output, or a scientific gap. The CSV is a derived field sample, so the manifest lists the original response hashes rather than a separate CSV response.

Source filenames and bytes are unchanged from the design package. A source response may contain incomplete, revised, or uncertain metadata.

## Data reuse

- OpenAlex metadata is distributed under CC0. See the [OpenAlex data documentation](https://help.openalex.org/api/).
- Crossref bibliographic metadata is generally reusable, while some abstracts retain publisher or author copyright. The supplied Crossref response contains no abstract. See [Crossref metadata reuse guidance](https://www.crossref.org/documentation/retrieve-metadata/rest-api/).
- ROR is planned as optional enrichment. No ROR response is included in this pilot. See the [ROR data dump licence](https://ror.readme.io/docs/data-dump).

The repository's MIT licence covers project code, not ownership of third-party source records or linked article content.

Full raw collections, local data, logs, and database dumps belong in ignored directories. Commit only small samples with their provenance.
