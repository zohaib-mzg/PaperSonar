# Database design status

The SQL in `schema/001_initial_schema.sql` is the original proposed PostgreSQL publication-centered model from Phase 1. It is **not a Phase 2 implementation**, has not been shown to be loaded with a full corpus, and does not represent the complete source-neutral five-source model by itself.

Before Phase 2 starts:

1. Review `docs/architecture/README.md` and the v2 logical dictionary.
2. Approve canonical research output, source record crosswalk, output version, typed output relationship, dated observation and per-source sync-state grains.
3. Split the physical design into the course-required `project_staging`, `project_dw`, and `project_reporting` schemas.
4. Decide how the original publication mart is built from the canonical model.
5. Add key, allocation, identity-conflict, snapshot publication and deletion/reconciliation rules.
6. Test the model against representative records from all five source shapes before a full extraction.

No database has been populated by this repository update. No ETL or reporting scripts have been implemented.
