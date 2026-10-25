# Database design

[001_initial_schema.sql](schema/001_initial_schema.sql) is the proposed PostgreSQL physical model. It defines the `papersonar` schema, 15 tables, key constraints, initial unknown members, and selected indices.

## Status

This is a design artifact. PostgreSQL execution, source-dependent loading, and report queries remain implementation work. Do not interpret the schema file as a completed pipeline or a migration for an existing populated database.

When implementation begins, apply it to an empty development database and validate its constraints before importing source data. The first script is not designed for repeated execution against already-created tables.

## Modeling rules

- Keep one publication fact per admitted canonical work.
- Select one observation date when aggregating cumulative citation counts.
- Keep out-of-scope reference targets as work stubs without publication facts.
- Deduplicate institutional affiliations across authors before assigning fractional weights.
- Do not join several multivalued bridges without controlling the work grain.
- Current dimensions and memberships use Type 1 updates. Reproduce earlier classification states from retained inputs.

Add analytical SQL under `database/queries/` when it exists. Add versioned migration scripts after implementation starts rather than silently editing an applied schema.
