# Initial warehouse design

Date: 25 October 2026  
Status: proposed design baseline

## Context

PaperSonar needs comparisons across publications, topics, dates, venues, and research communities. The initial system must operate with local resources and a free source-access budget. Publication events, later observations, and reference relationships do not share the same row meaning.

## Decisions

1. Use PostgreSQL for staging, dimensional storage, and analytical views. Begin with Python batch extraction and Power BI Desktop reporting.
2. Separate the publication transaction fact, work observation snapshot fact, and factless citation relationship fact.
3. Use stable source identities as alternate keys and integer warehouse keys for relationships. Treat DOI conflicts as reconciliation work.
4. Use bridges for supplied topic, author, and institution relationships. Deduplicate institutions across authorships before allocating fractional credit.
5. Store cumulative citation counts at an explicit observation grain. Never sum them across observation dates.
6. Use Type 1 current metadata and preserve raw inputs and dated report exports. Earlier classification states require a rebuild from archived evidence.
7. Refresh a declared bounded corpus without relying on paid change-tracking filters. Publish observations only after a validated successful run.
8. Keep reference targets outside the admitted corpus as stubs. Do not count those targets as publication output.

## Consequences

The first warehouse stays manageable and its measures have explicit denominators. Older citation observations survive, but joining them to current dimensions does not reproduce a past classification state. Broad discipline coverage and versioned membership history are later extensions.

The product will expose candidate intersections and their evidence. It will not treat bibliometric sparsity as verified scientific novelty.

## Related definitions

- [Full scope](../project-scope.md)
- [Model diagrams and definitions](../architecture/README.md)
- [Source plan](../sources.md)
- [Data dictionary](../submissions/phase-1/data-dictionary.xlsx)
