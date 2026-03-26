# oracle-query-fragment-governance Specification

## Purpose
TBD - created by archiving change residual-hardening-round4. Update Purpose after archive.
## Requirements
### Requirement: Shared Oracle Query Fragments SHALL Have a Single Source of Truth
Cross-service Oracle query fragments for resource and equipment cache loading MUST be defined in a shared module and imported by service implementations.

#### Scenario: Update common table/view reference
- **WHEN** a common table or view name changes
- **THEN** operators and developers MUST be able to update one shared definition without editing duplicated SQL literals across services

### Requirement: Service Queries MUST Preserve Existing Columns and Semantics
Services consuming shared Oracle query fragments SHALL preserve existing selected columns, filters, and downstream payload behavior.

#### Scenario: Resource and equipment cache refresh after refactor
- **WHEN** cache services execute queries via shared fragments
- **THEN** resulting payload structure MUST remain compatible with existing aggregation and API contracts

### Requirement: Lineage SQL fragments SHALL be centralized in `sql/lineage/` directory
Split ancestor and merge source SQL queries SHALL be defined in `sql/lineage/` and shared across services via `SQLLoader`.

#### Scenario: Mid-section-defect lineage query
- **WHEN** `mid_section_defect_service.py` needs split ancestry or merge source data
- **THEN** it SHALL call `LineageEngine` which loads SQL from `sql/lineage/split_ancestors.sql` and `sql/lineage/merge_sources.sql`
- **THEN** it SHALL NOT use `sql/mid_section_defect/split_chain.sql` or `sql/mid_section_defect/genealogy_records.sql`

#### Scenario: Deprecated SQL file handling
- **WHEN** `sql/mid_section_defect/genealogy_records.sql` and `sql/mid_section_defect/split_chain.sql` are deprecated
- **THEN** the files SHALL be marked with a deprecated comment at the top
- **THEN** grep SHALL confirm zero `SQLLoader.load` references to these files
- **THEN** the files SHALL be retained for one version before deletion

### Requirement: All user-input SQL queries SHALL use QueryBuilder bind params
`_build_in_filter()` and `_build_in_clause()` in `query_tool_service.py` SHALL be fully replaced by `QueryBuilder.add_in_condition()`.

#### Scenario: Complete migration to QueryBuilder
- **WHEN** the refactoring is complete
- **THEN** grep for `_build_in_filter` and `_build_in_clause` SHALL return zero results
- **THEN** all queries involving user-supplied values SHALL use `QueryBuilder.params`

