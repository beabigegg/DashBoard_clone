## Purpose

Data integrity probes that verify row count consistency across API responses, pagination, and database baselines for all heavy-query services.

## Requirements

### Requirement: Integrity probes SHALL verify row count consistency via three-point verification
Each data integrity probe SHALL compare row counts at three checkpoints: (1) pre-query COUNT(*) baseline, (2) API response `total_rows`, and (3) sum of all paginated page rows.

#### Scenario: Row count matches across all three checkpoints
- **WHEN** a query with known filter criteria is executed
- **THEN** `COUNT(*)` baseline, API `total_rows`, and `sum(page_rows)` SHALL agree within the configured tolerance (`STRESS_ROW_COUNT_TOLERANCE_PCT`, default 0.1%)
- **THEN** the probe SHALL report "PASS" with all three values

#### Scenario: API total_rows is significantly less than COUNT(*) baseline
- **WHEN** `total_rows` is more than `STRESS_ROW_COUNT_TOLERANCE_PCT` below the COUNT(*) baseline
- **THEN** the probe SHALL report "FAIL -- silent data loss detected"
- **THEN** the report SHALL include the deficit count and percentage

#### Scenario: Pagination sum does not match API total_rows
- **WHEN** the sum of rows across all pages differs from `total_rows`
- **THEN** the probe SHALL report "FAIL -- pagination integrity violation"
- **THEN** the report SHALL include the expected vs actual row count and which page range was affected

#### Scenario: COUNT(*) baseline query fails
- **WHEN** the pre-query COUNT(*) fails (timeout, connection error)
- **THEN** the baseline checkpoint SHALL be skipped
- **THEN** the probe SHALL fall back to two-point verification (API total_rows vs pagination sum)

### Requirement: Reject History integrity probe SHALL verify batch merge completeness across quarterly date ranges
A probe SHALL exercise reject-history queries using a minimum date span of **1 quarter (90 days)** to reflect realistic production usage, cross the batch decomposition threshold, and verify merged results are complete.

#### Scenario: One-quarter time-range batch merge integrity (90 days, ~9 chunks)
- **WHEN** a reject-history query spans 90 days (decomposed into ~9 chunks of 10 days each)
- **THEN** the merged `total_rows` SHALL match the COUNT(*) baseline within tolerance
- **THEN** no `partial_failure` metadata SHALL be present in the response

#### Scenario: One-year time-range batch merge integrity (365 days, ~37 chunks)
- **WHEN** a reject-history query spans 365 days
- **THEN** the merged `total_rows` SHALL match the COUNT(*) baseline within tolerance
- **THEN** if dataset does not cover a full year, the test SHALL be marked `pytest.skip`

#### Scenario: ID-batch merge integrity
- **WHEN** a reject-history query includes 1500 lot IDs (decomposed into 2 batches of 1000+500)
- **THEN** the merged `total_rows` SHALL match the COUNT(*) baseline within tolerance

#### Scenario: Partial batch failure detected
- **WHEN** the response contains `partial_failure` or `has_partial_failure` metadata
- **THEN** the probe SHALL report "WARNING -- partial failure" with the declared missing chunk count
- **THEN** the row deficit SHALL be cross-checked against the baseline to verify the partial failure metadata is accurate

### Requirement: Production History integrity probe SHALL detect silent truncation via async path
A probe SHALL exercise production-history queries through the **async RQ path** (202 -> polling -> spool hit) that approach the `max_total_rows` limit and verify results are not silently truncated.

#### Scenario: One-quarter query via async path -- baseline integrity (90 days)
- **WHEN** a production-history query spanning 90 days is submitted, receives HTTP 202, completes via polling
- **THEN** `total_rows` SHALL match the COUNT(*) baseline within tolerance

#### Scenario: One-year query via async path -- near truncation limit (365 days)
- **WHEN** a production-history query spanning 365 days returns rows approaching `max_total_rows` (within 10%) via the async path
- **THEN** the probe SHALL verify whether truncation occurred by comparing against COUNT(*) baseline
- **THEN** if truncated, the probe SHALL report "FAIL -- silent truncation at max_total_rows boundary"
- **THEN** if dataset does not cover a full year, the test SHALL be marked `pytest.skip`

#### Scenario: Async job failure does not produce partial spool
- **WHEN** a production-history async job fails mid-execution
- **THEN** no partial spool SHALL be registered in Redis
- **THEN** the probe SHALL verify by re-querying (should get 202 for fresh job, not 200 with corrupt data)

#### Scenario: Insufficient data volume for truncation probe
- **WHEN** the dataset cannot produce enough rows to approach the truncation limit
- **THEN** the test SHALL be marked as `pytest.skip` with a descriptive reason

### Requirement: Spool pagination integrity probe SHALL verify no data loss during page traversal
A probe SHALL execute a query that produces spooled results, then walk all pages and verify the total row sum matches the declared total.

#### Scenario: Full pagination walkthrough on hold-history
- **WHEN** a hold-history query returns >5000 rows (triggers spool)
- **THEN** walking all pages with `page_size=500` SHALL yield `sum(page_rows) == total_rows`

#### Scenario: Full pagination walkthrough on reject-history
- **WHEN** a reject-history query returns spooled results
- **THEN** walking all pages SHALL yield `sum(page_rows) == total_rows`
- **THEN** no page SHALL return an error or empty result before the last page

#### Scenario: Spool TTL expiration during pagination
- **WHEN** a query result is spooled and the test waits until TTL approaches expiration (if feasible in test environment)
- **THEN** subsequent page requests SHALL return a clear error (not empty data)
- **THEN** the probe SHALL report whether the error is user-visible or silent

### Requirement: Query Tool integrity probe SHALL verify ID batch merge completeness
A probe SHALL send a query-tool request with >1000 container IDs and verify all IDs appear in the merged result.

#### Scenario: Batch merge covers all requested IDs
- **WHEN** a query-tool request includes 1500 known-valid container IDs
- **THEN** the response SHALL contain results for all 1500 IDs (or a documented subset if some IDs have no data)
- **THEN** the probe SHALL cross-reference the result container IDs against the input list to detect missing entries

#### Scenario: Batch merge with some invalid IDs
- **WHEN** a query-tool request includes 1200 valid IDs and 300 non-existent IDs
- **THEN** the response SHALL contain results for exactly the 1200 valid IDs
- **THEN** no valid ID SHALL be silently dropped due to batch boundary splitting

### Requirement: Yield Alert integrity probe SHALL verify concurrent query completeness
A probe SHALL submit multiple yield-alert queries concurrently and verify each returns complete data despite contention for heavy-query slots.

#### Scenario: Concurrent yield-alert queries under slot contention
- **WHEN** 3 yield-alert queries are submitted concurrently (matching the `HEAVY_QUERY_MAX_CONCURRENT=3` slot limit)
- **THEN** all 3 queries SHALL eventually return results (may queue)
- **THEN** each result SHALL pass the three-point row count verification

#### Scenario: Yield-alert query rejected by slow-query gate
- **WHEN** a yield-alert query is rejected due to `slow_query_active_threshold`
- **THEN** the rejection SHALL be returned as an explicit HTTP error (503), NOT as an empty result
- **THEN** the probe SHALL verify the error response includes `retry_after_seconds`

### Requirement: Data integrity report SHALL summarize probe results per service
The `pytest_terminal_summary` hook SHALL include a "Data Integrity Summary" section.

#### Scenario: All integrity probes pass
- **WHEN** all data integrity probes pass
- **THEN** the summary SHALL list each service with "OK", the verified row count, and the verification method used

#### Scenario: Integrity probe detects data loss
- **WHEN** one or more probes detect row count mismatch
- **THEN** the summary SHALL list the affected service with "DATA LOSS", the expected vs actual row count, the deficit percentage, and which checkpoint failed (baseline/pagination/spool)

#### Scenario: Integrity probe skipped due to insufficient data
- **WHEN** a probe is skipped (dataset too small)
- **THEN** the summary SHALL list the service with "SKIPPED" and the reason
