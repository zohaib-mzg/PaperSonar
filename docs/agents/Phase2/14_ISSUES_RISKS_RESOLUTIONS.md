# Issues, Risks, and Resolutions Register

Review this register before each backfill and release. Owner roles are proposed and may be mapped to named team members in repository configuration.

| Risk | Likelihood | Impact | Mitigation | Owner | Detection |
|---|---|---|---|---|---|
| Trial expires | Medium | High: warehouse unavailable | Early backfill, evidence capture, exports, conversion decision | Project lead | Expiry checklist |
| Credit exhaustion | Medium | High | Resource monitor, XS warehouse, bounded retries, cost ledger | Admin | Usage/credit review |
| Cortex daily cap or cost | High if enabled | Medium/high | Feature OFF by default; hard budget and stop rule | Data engineer | Usage ledger |
| No outbound network from Snowflake | High per project assumptions | High if API calls are attempted in SQL | Extract externally in GitHub Actions | Architect | Integration smoke test |
| API rate limit or ban | Medium | High | Polite pacing, User-Agent where appropriate, 429 handling, backoff | Source adapter owner | HTTP status metrics |
| GitHub job/time limit | Medium | High | Six-hour budget, resumable cursors, file checkpoints | DevOps | Job duration/failure |
| COPY load-history retention | Medium | Medium | Bronze MERGE is durable idempotency guard; verify retention | Data engineer | Replay test |
| Duplicate MERGE source rows | Medium | High | QUALIFY dedupe, deterministic ordering, merge error setting | Data engineer | SQL test/task failure |
| Surrogate-key instability | Medium | High | MERGE by business key; never truncate dimensions | DW owner | Before/after key test |
| Concurrent extract and transform | Medium | High | LOADED state, safe batch claim, immutable manifest | Orchestrator owner | Concurrent-run test |
| Oversized VARIANT record | Low/medium | Medium | Detect, quarantine, preserve error artifact | Source adapter owner | Oversize counter |
| JSON schema drift | High | Medium/high | Explicit expected keys and drift log; critical required-key gate | Data engineer | Drift query |
| Abstract reconstruction cost | Medium | Medium | Enable only if required; batch-scoped set-based SQL | Silver owner | Query duration/credits |
| Cross-source overlap | High | High for counts | Canonical crosswalk; do not sum raw source counts | DW owner | Duplicate/identity report |
| Citation-count volatility | High | Medium | Store source-specific snapshots and dates | DW owner | Cross-source comparison |
| Retractions/withdrawals | Medium | High | Preserve flags and source observations; do not delete history | Silver owner | Status change check |
| Timezone inconsistency | Medium | Medium | UTC convention; explicit timestamp conversions | Data engineer | Timestamp tests |
| Metadata/abstract licensing | Medium | High | Review each source's terms; store only permitted fields | Project lead | Source review checklist |
| Secrets leakage | Low | Critical | GitHub Secrets, least privilege, log redaction, rotation | Security owner | Secret scanning/log review |
| Force-push mistake | Medium | Critical | Tag, backup branch, inspect remote, use force-with-lease | Repository owner | Pre-push checklist |
| Git-stage access/privacy limits | Medium | High | Verify account integration, privileges, path behavior before design lock | Snowflake admin | Live smoke test |
| SQLFluff dialect gaps | Medium | Low/medium | Pin version, document intentional exclusions, still run Snowflake tests | CI owner | CI lint results |
| Silent task failure | Medium | High | Run log, task history checks, alerts, finalizer and publication gate | Orchestrator owner | Task history/DQ |
| Bulk source data impractical | Medium | High | Evaluate download size/license/freshness before committing | Source owner | Pilot download |
| Inferred identity is wrong | Medium | High | Match confidence, provenance, manual review, reversible crosswalk | Silver owner | Sample review |
| Late-arriving dimensions | Medium | Medium | Inferred members and deferred fact updates | DW owner | Unresolved-key DQ |
| Schema changes break SQL | Medium | High | Drift detection, versioned DDL, tests against fixtures | Data engineer | CI/DRIFT logs |

## Decision process
For every high-impact risk, record a mitigation owner, due date, test evidence, and residual risk. `VERIFY:` means the linked official documentation and target account/source behavior must be checked before claiming the issue is resolved.

## References
- Snowflake tasks: https://docs.snowflake.com/en/user-guide/tasks-intro
- Snowflake load considerations: https://docs.snowflake.com/en/user-guide/data-load-considerations-load
- Snowflake security: https://docs.snowflake.com/en/user-guide/security-access-control-overview
- GitHub Actions security: https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions
- OpenAlex: https://docs.openalex.org/
- Crossref: https://www.crossref.org/documentation/retrieve-metadata/rest-api/
- arXiv: https://info.arxiv.org/help/api/user-manual.html
- DataCite: https://support.datacite.org/docs/api
- Zenodo: https://developers.zenodo.org/
