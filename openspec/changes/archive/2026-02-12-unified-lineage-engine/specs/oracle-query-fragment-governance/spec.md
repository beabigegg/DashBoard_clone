## ADDED Requirements

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
