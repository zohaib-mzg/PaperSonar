-- =============================================================================
-- Purpose: Seed the versioned taxonomy and weighted keyword rules that drive
--          deterministic categorization. Mirrors config/taxonomy.yml.
-- Inputs: PROJECT_REF tables.
-- Outputs: REF_CATEGORY and REF_CATEGORY_KEYWORD rows.
-- Idempotent: Yes - MERGE on CATEGORY_KEY / RULE_ID.
-- Owner: PAPERSONAR_TRANSFORMER
-- Parameters: None.
-- Cost: Metadata only.
-- =============================================================================
-- Cortex is deliberately not used. Scoring is title x3 and source keyword/topic
-- x2. Abstract x1 is reserved and disabled until a safe abstract source exists.

MERGE INTO PAPERSONAR.PROJECT_REF.REF_CATEGORY t
USING (
  SELECT column1 AS CATEGORY_KEY, column2 AS LABEL, column3 AS PARENT_KEY
  FROM VALUES
    ('ai-ml', 'Artificial Intelligence and Machine Learning', NULL),
    ('llm', 'Large Language Models', 'ai-ml'),
    ('rag', 'Retrieval-Augmented Generation', 'llm'),
    ('ai-agents', 'AI Agents', 'llm'),
    ('code-generation', 'Code Generation', 'ai-ml'),
    ('program-repair', 'Program Repair', 'software-engineering'),
    ('software-testing', 'Software Testing', 'software-engineering'),
    ('software-maintenance', 'Software Maintenance', 'software-engineering'),
    ('program-analysis', 'Program Analysis', 'software-engineering'),
    ('developer-tools', 'Developer Tools', 'software-engineering'),
    ('mlops', 'MLOps', 'software-engineering'),
    ('data-engineering', 'Data Engineering', 'software-engineering'),
    ('databases', 'Databases', 'software-engineering'),
    ('security-privacy', 'Security and Privacy', 'software-engineering'),
    ('requirements-engineering', 'Requirements Engineering', 'software-engineering'),
    ('software-architecture', 'Software Architecture', 'software-engineering'),
    ('empirical-software-engineering', 'Empirical Software Engineering', 'software-engineering'),
    ('human-computer-interaction', 'Human-Computer Interaction', 'software-engineering'),
    ('distributed-systems', 'Distributed Systems', 'software-engineering'),
    ('software-engineering', 'Software Engineering', NULL),
    ('unclassified', 'Unclassified', NULL)
) s
ON t.CATEGORY_KEY = s.CATEGORY_KEY
WHEN MATCHED THEN UPDATE SET
  t.LABEL = s.LABEL, t.PARENT_KEY = s.PARENT_KEY,
  t.IS_ACTIVE = TRUE, t.TAXONOMY_VERSION = 'v1'
WHEN NOT MATCHED THEN INSERT
  (CATEGORY_KEY, LABEL, PARENT_KEY, IS_ACTIVE, TAXONOMY_VERSION)
  VALUES (s.CATEGORY_KEY, s.LABEL, s.PARENT_KEY, TRUE, 'v1');

MERGE INTO PAPERSONAR.PROJECT_REF.REF_CATEGORY_KEYWORD t
USING (
  SELECT column1 AS RULE_ID, column2 AS CATEGORY_KEY, column3 AS PATTERN,
         column4 AS FIELD_NAME
  FROM VALUES
    ('KW-001', 'rag', 'retrieval augmented generation', 'title'),
    ('KW-002', 'rag', 'retrieval-augmented generation', 'title'),
    ('KW-003', 'rag', 'rag', 'title'),
    ('KW-004', 'llm', 'large language model', 'title'),
    ('KW-005', 'llm', 'llm', 'title'),
    ('KW-006', 'ai-agents', 'ai agent', 'title'),
    ('KW-007', 'ai-agents', 'agentic', 'title'),
    ('KW-008', 'code-generation', 'code generation', 'title'),
    ('KW-009', 'code-generation', 'code completion', 'title'),
    ('KW-010', 'program-repair', 'program repair', 'title'),
    ('KW-011', 'program-repair', 'automated repair', 'title'),
    ('KW-012', 'software-testing', 'software testing', 'title'),
    ('KW-013', 'software-testing', 'test generation', 'title'),
    ('KW-014', 'software-testing', 'mutation testing', 'title'),
    ('KW-015', 'software-maintenance', 'software maintenance', 'title'),
    ('KW-016', 'software-maintenance', 'code refactoring', 'title'),
    ('KW-017', 'program-analysis', 'program analysis', 'title'),
    ('KW-018', 'program-analysis', 'static analysis', 'title'),
    ('KW-019', 'developer-tools', 'developer tool', 'title'),
    ('KW-020', 'developer-tools', 'ide', 'keywords'),
    ('KW-021', 'mlops', 'mlops', 'title'),
    ('KW-022', 'mlops', 'machine learning operations', 'title'),
    ('KW-023', 'data-engineering', 'data pipeline', 'title'),
    ('KW-024', 'data-engineering', 'data engineering', 'title'),
    ('KW-025', 'data-engineering', 'etl', 'keywords'),
    ('KW-026', 'databases', 'database', 'title'),
    ('KW-027', 'databases', 'query optimization', 'title'),
    ('KW-028', 'security-privacy', 'vulnerability', 'title'),
    ('KW-029', 'security-privacy', 'privacy', 'title'),
    ('KW-030', 'requirements-engineering', 'requirements engineering', 'title'),
    ('KW-031', 'software-architecture', 'software architecture', 'title'),
    ('KW-032', 'software-architecture', 'microservice', 'title'),
    ('KW-033', 'empirical-software-engineering', 'empirical study', 'title'),
    ('KW-034', 'human-computer-interaction', 'human computer interaction', 'title'),
    ('KW-035', 'human-computer-interaction', 'usability', 'title'),
    ('KW-036', 'distributed-systems', 'distributed system', 'title'),
    ('KW-037', 'distributed-systems', 'consensus', 'title')
) s
ON t.RULE_ID = s.RULE_ID
WHEN MATCHED THEN UPDATE SET
  t.CATEGORY_KEY = s.CATEGORY_KEY, t.PATTERN = s.PATTERN,
  t.FIELD_NAME = s.FIELD_NAME, t.BASE_WEIGHT = 1.00,
  t.IS_ACTIVE = TRUE, t.RULE_VERSION = 'v1'
WHEN NOT MATCHED THEN INSERT
  (RULE_ID, CATEGORY_KEY, PATTERN, FIELD_NAME, BASE_WEIGHT, IS_ACTIVE, RULE_VERSION)
  VALUES (s.RULE_ID, s.CATEGORY_KEY, s.PATTERN, s.FIELD_NAME, 1.00, TRUE, 'v1');
