## ADDED Requirements

### Requirement: EventFetcher SHALL support iterator mode for streaming
`EventFetcher.fetch_events_iter()` SHALL yield batched results for streaming consumption.

#### Scenario: Iterator mode yields batches
- **WHEN** `fetch_events_iter(container_ids, domain, batch_size)` is called
- **THEN** it SHALL yield `Dict[str, List[Dict]]` batches (grouped by CONTAINERID)
- **THEN** each yielded batch SHALL contain results from one `cursor.fetchmany()` call
- **THEN** memory usage SHALL be proportional to `batch_size`, not total result count

#### Scenario: Iterator mode cache behavior
- **WHEN** `fetch_events_iter` is used for large CID sets (> CACHE_SKIP_CID_THRESHOLD)
- **THEN** per-domain cache SHALL be skipped (consistent with `fetch_events` behavior)
