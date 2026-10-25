# PaperSonar architecture

The model separates publication output, dated work observations, and directed reference relationships. The attribution bridges keep repeated authors, institutions, and topic assignments outside the publication grain.

| Diagram | PNG | PDF |
| --- | --- | --- |
| Data architecture | [PNG](diagrams/01_Data_architecture.png) | [PDF](diagrams/01_Data_architecture.pdf) |
| Conceptual model | [PNG](diagrams/02_Conceptual_model.png) | [PDF](diagrams/02_Conceptual_model.pdf) |
| Dimensional overview | [PNG](diagrams/03_Dimensional_schema.png) | [PDF](diagrams/03_Dimensional_schema.pdf) |
| Physical dimensions | [PNG](diagrams/04_Physical_dimensions.png) | [PDF](diagrams/04_Physical_dimensions.pdf) |
| Physical facts and bridges | [PNG](diagrams/05_Physical_facts_and_bridges.png) | [PDF](diagrams/05_Physical_facts_and_bridges.pdf) |
| Complete warehouse relationships | [PNG](diagrams/06_Complete_relationships.png) | [PDF](diagrams/06_Complete_relationships.pdf) |

## Editable definitions

- [Model explanation in Word](model-design.docx)
- [Model explanation in PDF](model-design.pdf)
- [DBML source](papersonar.dbml), suitable for import into dbdiagram.io
- [PostgreSQL physical schema](../../database/schema/001_initial_schema.sql)
- [Excel data dictionary](../submissions/phase-1/data-dictionary.xlsx)

The complete relationship diagram shows all business FK connections. Operational lineage FKs are listed in its note and the relationship register. The physical sheets supply field types, while the dictionary supplies definitions and source mappings.
