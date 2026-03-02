## MODIFIED Requirements

### Requirement: Detection query SHALL use BatchQueryEngine for long-range decomposition

The `_fetch_station_detection_data()` function SHALL delegate to BatchQueryEngine when the requested date range exceeds the configurable threshold, preventing Oracle timeout on large detection queries.

#### Scenario: Long date range triggers engine decomposition
- **WHEN** `_fetch_station_detection_data(start_date, end_date, station)` is called
- **AND** the date range exceeds `BATCH_QUERY_TIME_THRESHOLD_DAYS` (default 60)
- **THEN** the date range SHALL be decomposed via `decompose_by_time_range()`
- **THEN** each chunk SHALL be executed through the existing detection SQL with chunk-scoped dates
- **THEN** chunk results SHALL be cached in Redis and merged into a single DataFrame

#### Scenario: Short date range preserves direct path
- **WHEN** the date range is within the threshold
- **THEN** the existing direct query path SHALL be used with zero overhead

#### Scenario: Memory guard protects against oversized detection results
- **WHEN** a single chunk result exceeds `BATCH_CHUNK_MAX_MEMORY_MB`
- **THEN** that chunk SHALL be discarded and marked as failed
- **THEN** remaining chunks SHALL continue executing
- **THEN** the batch metadata SHALL reflect `has_partial_failure`
