## MODIFIED Requirements

### Requirement: EventFetcher SHALL use streaming fetch for batch queries
`EventFetcher._fetch_batch` SHALL use `read_sql_df_slow_iter` (fetchmany-based iterator) instead of `read_sql_df` (fetchall + DataFrame) to reduce peak memory usage.

#### Scenario: Batch query memory optimization
- **WHEN** EventFetcher executes a batch query for a domain
- **THEN** the query SHALL use `cursor.fetchmany(batch_size)` (env: `DB_SLOW_FETCHMANY_SIZE`, default: 5000) instead of `cursor.fetchall()`
- **THEN** rows SHALL be converted directly to dicts via `dict(zip(columns, row))` without building a DataFrame
- **THEN** each fetchmany batch SHALL be grouped into the result dict immediately, allowing the batch rows to be garbage collected

#### Scenario: Existing API contract preserved
- **WHEN** EventFetcher.fetch_events() returns results
- **THEN** the return type SHALL remain `Dict[str, List[Dict[str, Any]]]` (grouped by CONTAINERID)
- **THEN** the result SHALL be identical to the previous DataFrame-based implementation
