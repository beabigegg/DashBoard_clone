# reject-query-backpressure Specification

## Purpose
Protect reject-history primary query capacity through endpoint backpressure and pre-flight memory admission checks.

## Requirements
### Requirement: POST /api/reject-history/query SHALL enforce rate limiting
The reject-history query endpoint SHALL apply a configurable rate limit to prevent concurrent overload of the batch query engine.

#### Scenario: Rate limit configuration
- **WHEN** the application starts
- **THEN** a rate limiter SHALL be configured with bucket `reject-history-query`
- **THEN** `REJECT_HISTORY_QUERY_RATE_LIMIT_MAX_REQUESTS` env var SHALL control max attempts (default 10)
- **THEN** `REJECT_HISTORY_QUERY_RATE_LIMIT_WINDOW_SECONDS` env var SHALL control window (default 60)

#### Scenario: Request within limit
- **WHEN** fewer than 10 requests have been made in the current 60-second window
- **THEN** the request SHALL proceed normally

#### Scenario: Request exceeds limit
- **WHEN** 10 or more requests have been made in the current 60-second window
- **THEN** the endpoint SHALL return HTTP 429
- **THEN** the response SHALL include a `Retry-After` header

#### Scenario: Rate limit uses same pattern as existing endpoints
- **WHEN** the rate limiter is instantiated
- **THEN** it SHALL use `configured_rate_limit()` with the same interface as `_REJECT_HISTORY_LIST_RATE_LIMIT` and `_REJECT_HISTORY_EXPORT_RATE_LIMIT`

### Requirement: Reject primary query SHALL check RSS before execution
The `execute_primary_query()` function SHALL reject requests when worker RSS memory exceeds a configurable threshold, preventing the query from inflating memory further.

#### Scenario: RSS below threshold
- **WHEN** `process_rss_mb()` returns a value below `REJECT_QUERY_RSS_REJECT_MB` (default 900)
- **THEN** the query SHALL proceed normally

#### Scenario: RSS above threshold
- **WHEN** `process_rss_mb()` returns a value at or above `REJECT_QUERY_RSS_REJECT_MB`
- **THEN** `execute_primary_query()` SHALL raise `RejectPrimaryQueryOverloadError` with code `SERVICE_OVERLOADED`
- **THEN** the error SHALL include `retry_after=30`
- **THEN** the route handler SHALL return HTTP 503 with `Retry-After: 30` header

#### Scenario: RSS check occurs before query lock acquisition
- **WHEN** the RSS check triggers rejection
- **THEN** no query lock SHALL have been acquired
- **THEN** no Oracle query SHALL have been executed

#### Scenario: RSS threshold lower than trace/query-tool thresholds
- **WHEN** the default thresholds are used
- **THEN** `REJECT_QUERY_RSS_REJECT_MB` (900) SHALL be lower than `TRACE_SYNC_RSS_REJECT_MB` (1100) and `QUERY_TOOL_RSS_REJECT_MB` (1100)

#### Scenario: psutil unavailable
- **WHEN** `process_rss_mb()` returns `None`
- **THEN** the query SHALL proceed normally (fail-open)

### Requirement: Reject chunk execution SHALL enforce max_rows_per_chunk at SQL level
The `_run_reject_chunk()` function SHALL apply a SQL-level row limit using Oracle `ROWNUM` to prevent any single chunk from returning unbounded rows.

#### Scenario: SQL wrapping with ROWNUM
- **WHEN** `max_rows_per_chunk` is provided and truthy
- **THEN** the chunk SQL SHALL be wrapped as `SELECT * FROM ({original_sql}) WHERE ROWNUM <= {max_rows_per_chunk}`

#### Scenario: No max_rows_per_chunk
- **WHEN** `max_rows_per_chunk` is `None` or `0`
- **THEN** the chunk SQL SHALL NOT be wrapped with ROWNUM

#### Scenario: Truncation detection
- **WHEN** `max_rows_per_chunk` is provided
- **THEN** the function SHALL query for `max_rows_per_chunk + 1` rows
- **WHEN** the result contains exactly `max_rows_per_chunk + 1` rows
- **THEN** the function SHALL log a warning indicating truncation occurred
- **THEN** the function SHALL return only `max_rows_per_chunk` rows

#### Scenario: Result within limit
- **WHEN** `max_rows_per_chunk=50000` and the chunk returns 30000 rows
- **THEN** all 30000 rows SHALL be returned without modification
