## MODIFIED Requirements

### Requirement: EventFetcher SHALL support spool-oriented execution for migrated callers
EventFetcher and its callers SHALL support writing large domain results into spool-oriented stage outputs so that large result sets do not need to remain fully materialized in memory.

#### Scenario: Migrated caller uses spool-oriented path
- **WHEN** a caller has been migrated to the unified spool pipeline
- **THEN** EventFetcher output SHALL be suitable for stage spool persistence and downstream DuckDB processing

### Requirement: EventFetcher row guard retirement SHALL be gated
The existing total-row truncation guard SHALL only be removed after the relevant callers are fully migrated to spool-safe execution.

#### Scenario: Legacy caller still depends on in-memory result assembly
- **WHEN** a caller still assembles large event results in memory
- **THEN** the existing row guard SHALL remain until that path is retired

#### Scenario: Spool-safe path complete
- **WHEN** the caller has fully migrated to stage spool output and downstream DuckDB processing
- **THEN** the row truncation guard MAY be removed for that path
