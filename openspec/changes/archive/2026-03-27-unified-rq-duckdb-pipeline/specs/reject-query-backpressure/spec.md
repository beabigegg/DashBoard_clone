## MODIFIED Requirements

### Requirement: Reject query SHALL use unified spool pipeline without RSS guard
Reject query's async path SHALL be integrated into the unified spool pipeline. The independent RSS guard (`REJECT_QUERY_RSS_REJECT_MB`) SHALL be removed as the spool architecture prevents in-memory accumulation.

#### Scenario: Reject query routes to unified pipeline
- **WHEN** a reject-history query is initiated
- **THEN** if a valid spool exists, results SHALL be served from DuckDB
- **THEN** if no spool exists, the query SHALL be enqueued as an RQ job
- **THEN** the query SHALL NOT check `REJECT_QUERY_RSS_REJECT_MB` before execution

#### Scenario: Reject warmup via spool scheduler
- **WHEN** the spool warmup scheduler runs
- **THEN** reject_dataset SHALL be pre-loaded for 90 days (upgraded from 30 days)
- **THEN** reject queries within the 90-day range SHALL be served from DuckDB without RQ job
