# Versioned Topic Categorization

## Purpose
Assign explainable, multi-label categories to canonical research outputs even when a source supplies no category. Categorization runs in SQL and produces versioned evidence.

## Layered strategy
1. Source taxonomy mapping.
2. Weighted keyword/phrase/rule classifier.
3. Optional Cortex residual classification, feature-flagged OFF by default.
4. Optional propagation from references/related outputs, only with provenance and safeguards.
5. Fallback category `Unclassified`.

## Reference tables
`PROJECT_REF.REF_TAXONOMY_MAP`: source, source taxonomy value, internal category, mapping version, active flag.
`PROJECT_REF.REF_CATEGORY_KEYWORD`: category, phrase/regex, field weight, match weight, negative/context guards, rule version, active flag.
`PROJECT_REF.REF_CATEGORY`: stable category business key, label, parent category, description, active/version.
`PROJECT_REF.CATEGORY_OVERRIDE`: canonical output business key, category, override reason, reviewer, timestamps, active flag.

Initial internal taxonomy should cover software engineering and computing topics including: AI/ML, LLMs, retrieval-augmented generation (RAG), AI agents, code generation, program repair, software testing, software maintenance, program analysis, developer tools, MLOps, data engineering, databases, security/privacy, requirements engineering, software architecture, empirical software engineering, human-computer interaction, distributed systems, and `Unclassified`. Use parent-child relationships where useful.

## Weighted rules
Starting field weights: title x3, keywords/subjects x2, abstract x1. Scores are a documented sum of matched rule weights adjusted by field weight and negative/context guards. Normalize scores into a defined confidence scale only after evaluation; do not call raw scores calibrated probabilities.

Example:
- `retrieval-augmented generation` in title: strong RAG match.
- `RAG` in title: match only with case/context boundaries or companion terms that distinguish the acronym from unrelated use.
- A negative guard can suppress a rule when context indicates unrelated meaning.
- Source-provided taxonomy mapping is retained as a separate method and should not be silently overwritten by lexicon rules.

Store multi-label output in `BRIDGE_OUTPUT_TOPIC_CATEGORY` with `CATEGORY_KEY`, score, confidence band, method, `IS_PRIMARY`, rank, taxonomy version, and evidence/rule IDs. Enforce one primary category per canonical output using DQ checks and deterministic tie-breaking.

## Cortex option
Cortex embeddings/classification may be evaluated only for unclassified or low-confidence residual records. Feature flag defaults OFF. Apply a hard run budget and stop rule. Do not make it a dependency for baseline acceptance.
`VERIFY:` current trial restrictions, function availability, pricing, and daily cap against official Snowflake Cortex docs and actual account.

## Evaluation
Hand-label approximately 200 records across source types and categories. Keep labels out of the rule-tuning sample where possible. Calculate precision, recall, and F1 by category and method; inspect confusion cases and false acronym matches. Record evaluation date, taxonomy version, sample selection, labeler, and results. No unsupported claim of classifier accuracy.

## Acceptance
- Missing source category still receives a rule-based candidate or `Unclassified`.
- Every assignment has method/version/evidence.
- Multi-label bridge has one deterministic primary category.
- Manual overrides are auditable.
- Rules are tested against positive and negative examples.
- Cortex remains off unless explicitly enabled and budget-checked.

## References
- Snowflake Cortex AI: https://docs.snowflake.com/en/user-guide/snowflake-cortex/aisql
- OpenAlex topics: https://docs.openalex.org/
- arXiv API: https://info.arxiv.org/help/api/user-manual.html
- Crossref REST API: https://www.crossref.org/documentation/retrieve-metadata/rest-api/
- DataCite API: https://support.datacite.org/docs/api
- Zenodo API: https://developers.zenodo.org/
