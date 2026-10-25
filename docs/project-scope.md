# PaperSonar

Project scope and delivery plan

Design baseline 1.0   /   25 October 2026

PaperSonar will help researchers compare potential research directions using a bounded, inspectable collection of scholarly metadata. The first release delivers a local analytical warehouse and reports. A later application will let users save comparisons and examine the evidence behind them.

## The decision PaperSonar supports

A researcher choosing between software testing, software reliability and web security needs more than a list of relevant papers. PaperSonar will compare publication activity, citation cohorts, institutional participation and access to papers across those directions. Every comparison will identify its corpus, date cutoff and counting method. Users can then read the linked publications before deciding where to invest their time.

The initial focus is software engineering and closely related topics. This keeps the product distinct from a model benchmark or pricing observatory and gives the warehouse a coherent subject. Expansion to other disciplines will reuse the model after the first workflow proves useful.

## Product distinctions to test

- A dated comparison dossier with the exact corpus definition, supporting papers, metric version and coverage limits. A refresh produces a new dossier rather than silently replacing the old result.

- A comparison of growth, cohort citation impact and institutional concentration with counts and denominators visible. Users can inspect the underlying records.

- Sensitivity checks that compare primary-topic and fractional-topic counting. A direction whose rank changes substantially deserves closer examination.

- Candidate topic intersections accompanied by examples, parent-topic volumes and missingness. Users mark whether an intersection warrants a literature review.

These are product hypotheses. Litmaps already offers discovery and monitoring, and ResearchRabbit offers citation-based discovery [S10, S11]. The opportunity is the usefulness of this particular comparison workflow. Novelty and willingness to pay require user validation.

## Initial release scope

| Area | Committed baseline |
| --- | --- |
| Data | OpenAlex metadata for a frozen set of software-related topics. Crossref exact DOI checks. Optional ROR enrichment after the core import works. |
| Warehouse | PostgreSQL staging, three fact tables, eight dimensions, three bridges and a pipeline run log. |
| Analytics | Fourteen analytical questions, SQL views, a documented metric catalogue and five Power BI report pages. |
| Evidence | Retrieval manifests, raw response checksums, corpus and mapping versions, quality summaries and dated report exports. |
| Operations | Initial full load, restartable batch refresh, quota stop, idempotent reload and validation before publishing a run. |

The target is 30,000 to 60,000 distinct admitted works, subject to preflight counts and measured disk usage. This is an engineering target, not a source guarantee or submission requirement. If the selected topics are too large, narrow the topic set or date interval and document the change. Do not take the first N relevance-ranked results and describe them as a complete field.

The historical baseline covers publication years 2016 through 2025. A separate 2026 segment ends at the extraction date and is labelled partial. Baseline topic comparisons use completed years. The pilot supplied with this package is a 20-record keyword query from 2024 and is not the final corpus.

### Outside the first release

Full-text PDF ingestion, automatic scientific gap verification, an LLM writing assistant, citation-based researcher scoring, grant outcome prediction, real-time ingestion, payment processing and public multi-tenant accounts are outside the baseline. No paid API or GPU is required. A trained ML model is not necessary for the warehouse or its reporting.

## Sources and dataset contract

### OpenAlex as the primary source

Use /works for publication records and /topics for a controlled topic catalogue. Retain identifiers, titles, types, publication dates, primary and secondary topics, authorships, primary source, open access status, matched references and citation counts. OpenAlex releases its metadata under CC0 [S1, S5]. Do not interpret that licence as a licence to republish every linked article PDF.

Topic lookup returned T10743 Software Testing and Debugging Techniques, T12423 Software Reliability and Analysis Research, and T12479 Web Application Security Vulnerabilities. These are confirmed candidate IDs, not a frozen final topic selection. Inspect their descriptions and annual counts before admitting them. Start with these three topics and add up to three adjacent topics only if the data volume and relevance justify it.

For corpus membership, use any supplied topic matching an admitted topic ID so secondary-topic intersections are not discarded. Retain all supplied topics for admitted works. Query bounded topic and year partitions and union by canonical work ID. Topic labels are model-assigned metadata, so a co-assignment is not a semantic proof that a problem is unanswered [S6].

### Crossref for exact identifier reconciliation

Use the public /works/{doi} endpoint for exact DOI matches. Check DOI normalization, title and date discrepancies and deposited publication type. Keep the OpenAlex date unless a documented reconciliation rule and a retained Crossref response justify changing it. Crossref is not an independent citation ground truth because OpenAlex incorporates Crossref records. Exclude Crossref abstracts from redistributed samples unless their reuse terms are established [S8].

### ROR as optional enrichment

Use a known ROR ID already supplied in affiliation metadata to look up institutional names and geography. Never fuzzy-match an institution name automatically. ROR metadata is CC0 and available through its API and versioned dumps [S9]. ROR failure must not block the core publication import. Retain source institutions with unknown enrichment.

## Acquisition and refresh design

Create a free OpenAlex account for the production import and keep its key in an environment variable. Current documentation gives a free daily usage allowance. PaperSonar will impose a stricter application budget and stop before it is exhausted [S2]. No payment method or prepaid balance is part of the design. HTTP clients must redact the key from logs, including request URLs.

- Preflight each topic and year partition. Store the filters, response count, supported page size, extraction date and admitted work types. Use article, review and preprint records where the source type vocabulary supports them. Do not assume that all conference works share one separate type code.

- Use cursor paging with the documented supported page size of 100. Save the next cursor only after the raw page and manifest entry are durable. A free key is needed to follow cursor pages [S4].

- Write compressed JSON pages with SHA256 checksums. Stage rows with a run identifier, validate keys and source types, and quarantine malformed records with the reason.

- Load dimensions and reference stubs before facts. Resolve canonical OpenAlex identifiers, normalize DOIs and update bridges as complete work-level sets. Conflicting DOI identities enter reconciliation rather than merging on a title match.

- Publish a run only after reconciliation passes. Refresh one complete bounded corpus weekly initially. A smaller recent-publication overlap refresh can run between full scans, but is explicitly incomplete for older changes.

- The from_updated_date and from_created_date sync filters require paid access [S3]. The free design therefore uses bounded re-fetches, not a guaranteed incremental change feed. Snapshot history starts when PaperSonar begins collecting observations.

A failed partition does not create a corpus snapshot. Retain staging and resume its pages. Only complete successful runs publish a common observation day, noting the extraction start and end times. If a run crosses midnight UTC, assign the completion date to every snapshot row. A same-day rerun replaces that day only after complete validation. Later observation dates append rows.

Missing works are not automatically deleted. Reconcile canonical merges, source errors and scope changes first. Retain the raw evidence and publish a new corpus version for changed inclusion rules. A full refresh replaces the active reference set for each observed work and marks previously seen missing pairs inactive.

## Analytics and implementation plan

| Report page | Main content |
| --- | --- |
| Research activity | Annual publication counts, share change, growth and incomplete-year labels. |
| Citation context | Cohort medians at one snapshot date, within-work citation changes and revision flags. |
| Research communities | Institutional fractional output, author activity, concentration and citation flows. |
| Potential intersections | Topic-pair evidence, parent-topic volumes, supporting papers and method sensitivity. |
| Data coverage | Missing fields, source reconciliation exceptions, corpus definition and observation freshness. |

Power BI reads approved views from PostgreSQL. Start in Import mode for predictable local performance. Use single-direction relationships and role-played work and date views where needed. Pre-aggregate topic pairs and institution results in SQL. Do not expose unconstrained many-to-many joins as default report measures. Public Power BI sharing is not assumed to be free.

| Stage | Work and completion condition |
| --- | --- |
| Design baseline | Approve business questions, facts, grains, keys and corpus rules. This package supplies the proposed design. |
| Source profiling | Resolve candidate IDs, inspect type and date coverage, count partitions and set the final bounded corpus. |
| First load | Build staging and warehouse tables. Replay retained pages without duplicate facts. Reconcile counts with source partitions. |
| Historical observations | Publish at least two real successful observation dates. If time allows only one, demonstrate the structure and label citation change as unavailable. |
| Reporting | Implement the fourteen queries and five report pages. Check totals, denominators, unknown groups and drill-through records. |
| Release package | Provide configuration, dependency pins, SQL, ETL entry points, sample data, report files and reproducible run instructions. |

Use Python with a single HTTP client, PostgreSQL and pgAdmin, Git, and Power BI Desktop. Process one page at a time and use database batch inserts. Initial resource budgets are 2 GB for the database and 1 GB for compressed raw data, with a stop and review when either is reached. These are limits to measure against, not benchmarked consumption. Avoid Docker as a baseline requirement on constrained hardware.

## Public product and research scope

### Public application after the analytical release

Build a React interface and a FastAPI service on the same approved analytical views. Users select two or more directions, inspect counts and papers, save a private comparison and export a dated dossier. Begin with a public read-only demonstration using a small curated corpus. Add authentication, private notes, saved comparisons and request quotas when persistent hosting is available. Do not expose API keys or a direct write path to the warehouse.

Later additions may include DOI or BibTeX collection imports, version-to-version comparison, open-source self-hosting, institution portfolios and scheduled change notices. Notifications and user requests belong in a separate application schema. They must not change the grain of the research facts. Broad discipline coverage, full-text evidence and model-assisted summaries are separate decisions after usage and cost measurements.

### Demand validation and revenue

Test the workflow with five to eight researchers choosing a current research direction. Ask them to compare two topics using their normal method and PaperSonar, then record time to a defensible shortlist, useful missing evidence and whether the exported dossier helps a supervisor discussion. This is a planned test, not completed market research. Avoid collecting unpublished proposals unless consent and private storage are in place.

Possible paid features are shared laboratory workspaces, institutional reporting and hosted scheduled comparisons. Keep a reproducible self-hosted core available if adoption supports that route. Pricing, subscriptions and institutional willingness to pay remain unvalidated. Hosting and support can require funding even when the underlying software and data are free.

### Research questions worth investigating

A first study could measure how direction rankings change under primary versus fractional topic counting, incomplete reference coverage and different citation cohort windows. Use archived corpus versions and report rank correlation and the proportion of shortlist items that change. A later user study could compare decision time and evidence quality with ordinary paper search. Bibliometric sparsity alone cannot establish a research gap or a publishable scientific contribution.

### Main risks and release decisions

Source coverage, topic reclassification, citation age, missing affiliations and public hosting cost are the main risks. Freeze raw evidence and classification extraction dates. Publish coverage beside every comparison. Narrow the corpus if a full refresh cannot fit the free budget. Do not claim a historical classification state that was never captured. OpenAlex documented an October 2026 topic-assignment change, which makes this last constraint particularly relevant [S6].

## Source register and pilot evidence

The supporting data folder contains 20 real OpenAlex work records, a topic lookup response and one exact Crossref DOI response. The CSV is a field-level sample, not a research dataset or result. Retrieval URLs, timestamps and checksums are recorded in retrieval_manifest.json. The query searches software testing in publication year 2024 and therefore has relevance-order and keyword selection bias.

### Sources

[S1] OpenAlex API reference. https://help.openalex.org/api/

[S2] OpenAlex pricing and free daily allowance. https://help.openalex.org/access/pricing/

[S3] OpenAlex filter syntax and paid sync filters. https://help.openalex.org/api/filtering/

[S4] OpenAlex cursor pagination. https://help.openalex.org/api/paging/

[S5] OpenAlex works and bibliographic records. https://help.openalex.org/data/works/

[S6] OpenAlex topic hierarchy and October 2026 assignment change. https://help.openalex.org/data/topics/

[S7] OpenAlex citation coverage and citation measures. https://help.openalex.org/data/works/citations/

[S8] Crossref REST API and metadata reuse. https://www.crossref.org/documentation/retrieve-metadata/rest-api/

[S9] ROR registry releases and CC0 reuse. https://ror.readme.io/docs/data-dump

[S10] Litmaps discovery and monitoring features. https://www.litmaps.com/features

[S11] ResearchRabbit search and citation discovery. https://www.researchrabbit.ai/articles/guide-to-using-researchrabbit
