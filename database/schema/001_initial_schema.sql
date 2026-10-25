-- PaperSonar proposed PostgreSQL physical model 1.0

-- Design baseline. Execute against an empty database schema.

BEGIN;

CREATE SCHEMA IF NOT EXISTS papersonar;

SET search_path TO papersonar;

-- One pipeline execution
CREATE TABLE etl_run (
  run_id bigserial NOT NULL,
  started_at timestamptz NOT NULL,
  completed_at timestamptz,
  status text NOT NULL,
  corpus_version text NOT NULL,
  mapping_version text NOT NULL,
  metrics_version text NOT NULL,
  manifest_path text NOT NULL,
  config_sha256 char(64) NOT NULL,
  records_received integer NOT NULL,
  records_rejected integer NOT NULL,
  PRIMARY KEY (run_id)
);

-- One calendar day plus unknown member
CREATE TABLE dim_date (
  date_key integer NOT NULL,
  full_date date UNIQUE,
  day_of_month smallint,
  month_number smallint,
  quarter_number smallint,
  year_number smallint,
  PRIMARY KEY (date_key)
);

-- One OpenAlex topic
CREATE TABLE dim_topic (
  topic_key bigserial NOT NULL,
  openalex_topic_id text NOT NULL UNIQUE,
  topic_name text NOT NULL,
  subfield_id text,
  subfield_name text,
  field_id text,
  field_name text,
  domain_id text,
  domain_name text,
  PRIMARY KEY (topic_key)
);

-- One OpenAlex primary publication source
CREATE TABLE dim_venue (
  venue_key bigserial NOT NULL,
  openalex_source_id text NOT NULL UNIQUE,
  venue_name text NOT NULL,
  issn_l text,
  venue_type text,
  PRIMARY KEY (venue_key)
);

-- One source work type
CREATE TABLE dim_work_type (
  work_type_key bigserial NOT NULL,
  type_code text NOT NULL UNIQUE,
  type_label text NOT NULL,
  PRIMARY KEY (work_type_key)
);

-- One source open access status
CREATE TABLE dim_access_status (
  access_key bigserial NOT NULL,
  status_code text NOT NULL UNIQUE,
  is_oa boolean,
  PRIMARY KEY (access_key)
);

-- One OpenAlex author
CREATE TABLE dim_author (
  author_key bigserial NOT NULL,
  openalex_author_id text NOT NULL UNIQUE,
  author_name text NOT NULL,
  orcid text,
  PRIMARY KEY (author_key)
);

-- One OpenAlex institution
CREATE TABLE dim_institution (
  institution_key bigserial NOT NULL,
  openalex_institution_id text NOT NULL UNIQUE,
  ror_id text,
  institution_name text NOT NULL,
  country_code char(2),
  institution_type text,
  PRIMARY KEY (institution_key)
);

-- One canonical OpenAlex work including reference stubs
CREATE TABLE dim_work (
  work_key bigserial NOT NULL,
  openalex_work_id text NOT NULL UNIQUE,
  doi text,
  title text,
  publication_year smallint,
  date_precision text NOT NULL,
  language_code text,
  is_in_scope boolean NOT NULL,
  is_stub boolean NOT NULL,
  source_updated_at timestamptz,
  loaded_run_id bigint NOT NULL REFERENCES etl_run(run_id),
  PRIMARY KEY (work_key),
  CHECK (date_precision IN ('day','source_reported','year','unknown')),
  CHECK (NOT (is_stub AND is_in_scope))
);

-- One admitted canonical scholarly work
CREATE TABLE fact_publication (
  work_key bigint NOT NULL REFERENCES dim_work(work_key),
  publication_date_key integer NOT NULL REFERENCES dim_date(date_key),
  primary_topic_key bigint NOT NULL REFERENCES dim_topic(topic_key),
  venue_key bigint NOT NULL REFERENCES dim_venue(venue_key),
  work_type_key bigint NOT NULL REFERENCES dim_work_type(work_type_key),
  publication_count smallint NOT NULL,
  author_count integer,
  reference_count integer,
  loaded_run_id bigint NOT NULL REFERENCES etl_run(run_id),
  PRIMARY KEY (work_key),
  CHECK (publication_count = 1),
  CHECK (author_count >= 0),
  CHECK (reference_count >= 0)
);

-- One admitted work on one successfully published observation day
CREATE TABLE fact_work_snapshot (
  work_key bigint NOT NULL REFERENCES dim_work(work_key),
  snapshot_date_key integer NOT NULL REFERENCES dim_date(date_key),
  access_key bigint NOT NULL REFERENCES dim_access_status(access_key),
  cited_by_count integer,
  observed_count smallint NOT NULL,
  loaded_run_id bigint NOT NULL REFERENCES etl_run(run_id),
  PRIMARY KEY (work_key, snapshot_date_key),
  CHECK (cited_by_count >= 0),
  CHECK (observed_count = 1)
);

-- One distinct directed citing work and cited work pair observed in the retained corpus
CREATE TABLE fact_citation (
  citing_work_key bigint NOT NULL REFERENCES dim_work(work_key),
  cited_work_key bigint NOT NULL REFERENCES dim_work(work_key),
  first_seen_date_key integer NOT NULL REFERENCES dim_date(date_key),
  last_seen_run_id bigint NOT NULL REFERENCES etl_run(run_id),
  is_current boolean NOT NULL,
  PRIMARY KEY (citing_work_key, cited_work_key),
  CHECK (citing_work_key <> cited_work_key)
);

-- One work and supplied topic pair in current metadata
CREATE TABLE bridge_work_topic (
  work_key bigint NOT NULL REFERENCES dim_work(work_key),
  topic_key bigint NOT NULL REFERENCES dim_topic(topic_key),
  assignment_score numeric(8,6),
  is_primary boolean NOT NULL,
  allocation_weight numeric(12,10) NOT NULL,
  PRIMARY KEY (work_key, topic_key),
  CHECK (allocation_weight > 0 AND allocation_weight <= 1),
  CHECK (assignment_score >= 0 AND assignment_score <= 1)
);

-- One work and distinct supplied author pair
CREATE TABLE bridge_work_author (
  work_key bigint NOT NULL REFERENCES dim_work(work_key),
  author_key bigint NOT NULL REFERENCES dim_author(author_key),
  author_position text,
  PRIMARY KEY (work_key, author_key)
);

-- One work and distinct affiliated institution pair
CREATE TABLE bridge_work_institution (
  work_key bigint NOT NULL REFERENCES dim_work(work_key),
  institution_key bigint NOT NULL REFERENCES dim_institution(institution_key),
  allocation_weight numeric(12,10) NOT NULL,
  PRIMARY KEY (work_key, institution_key),
  CHECK (allocation_weight > 0 AND allocation_weight <= 1)
);

CREATE UNIQUE INDEX uq_work_doi ON dim_work(doi) WHERE doi IS NOT NULL;

CREATE UNIQUE INDEX uq_work_primary_topic ON bridge_work_topic(work_key) WHERE is_primary;

CREATE INDEX ix_publication_topic_date ON fact_publication(primary_topic_key, publication_date_key);

CREATE INDEX ix_snapshot_date ON fact_work_snapshot(snapshot_date_key);

CREATE INDEX ix_citation_target ON fact_citation(cited_work_key);

CREATE INDEX ix_work_year ON dim_work(publication_year);

INSERT INTO dim_date (date_key, full_date, day_of_month, month_number, quarter_number, year_number) VALUES (0, NULL, NULL, NULL, NULL, NULL);

INSERT INTO dim_topic (topic_key, openalex_topic_id, topic_name, subfield_id, subfield_name, field_id, field_name, domain_id, domain_name) VALUES (0, 'UNKNOWN', 'UNKNOWN', NULL, NULL, NULL, NULL, NULL, NULL);

INSERT INTO dim_venue (venue_key, openalex_source_id, venue_name, issn_l, venue_type) VALUES (0, 'UNKNOWN', 'UNKNOWN', NULL, NULL);

INSERT INTO dim_work_type (work_type_key, type_code, type_label) VALUES (0, 'UNKNOWN', 'UNKNOWN');

INSERT INTO dim_access_status (access_key, status_code, is_oa) VALUES (0, 'UNKNOWN', NULL);

INSERT INTO dim_author (author_key, openalex_author_id, author_name, orcid) VALUES (0, 'UNKNOWN', 'UNKNOWN', NULL);

INSERT INTO dim_institution (institution_key, openalex_institution_id, ror_id, institution_name, country_code, institution_type) VALUES (0, 'UNKNOWN', NULL, 'UNKNOWN', NULL, NULL);

COMMIT;

-- Source-dependent ETL, aggregate reconciliation and report exports are separate implementation work.