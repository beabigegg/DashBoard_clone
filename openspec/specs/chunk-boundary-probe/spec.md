## Purpose

Boundary probes that verify HTTP 413 enforcement at configured payload limits, result spillover behavior, batch query decomposition across quarterly date ranges, and telemetry counter diffing during stress runs.

## Requirements

### Requirement: Request payload boundary probes SHALL verify HTTP 413 at configured limits
`tests/stress/test_chunk_boundary.py` SHALL include parameterized tests that send requests at below, at, and above each request payload limit and verify correct HTTP responses.

#### Scenario: JSON body below limit (256 KB)
- **WHEN** a POST request is sent with a JSON body of ~200 KB
- **THEN** the response status SHALL NOT be 413

#### Scenario: JSON body above limit (256 KB)
- **WHEN** a POST request is sent with a JSON body of ~300 KB
- **THEN** the response status SHALL be 413
- **THEN** the response body SHALL contain an error code indicating payload too large

#### Scenario: Container ID batch below limit (200 IDs)
- **WHEN** a query-tool request is sent with 150 container IDs
- **THEN** the response status SHALL NOT be 413

#### Scenario: Container ID batch above limit (200 IDs)
- **WHEN** a query-tool request is sent with 250 container IDs
- **THEN** the response status SHALL be 413
- **THEN** the response body SHALL contain an error code indicating batch too large

#### Scenario: Resource detail limit below threshold (500)
- **WHEN** a resource detail request is sent with limit=400
- **THEN** the response status SHALL NOT be 413

#### Scenario: Resource detail limit above threshold (500)
- **WHEN** a resource detail request is sent with limit=600
- **THEN** the response status SHALL be 413

### Requirement: Result spillover boundary probes SHALL verify graceful degradation
Tests SHALL exercise queries that produce result sets near and above the spillover thresholds (48 MB / 200K rows) and verify that the system spills to Parquet without returning an error to the client.

#### Scenario: Query result below spillover threshold
- **WHEN** a query returns approximately 100K rows (below 200K threshold)
- **THEN** the response SHALL succeed with status 200
- **THEN** no Parquet spillover event SHALL be detected in telemetry counters

#### Scenario: Query result above spillover threshold
- **WHEN** a query returns approximately 250K rows (above 200K threshold)
- **THEN** the response SHALL succeed (status 200 or 202 with async job)
- **THEN** the telemetry counter for spool writes SHALL increment
- **THEN** no unhandled error SHALL be returned to the client

#### Scenario: Insufficient data for spillover probe
- **WHEN** the test dataset cannot produce enough rows to exceed the spillover threshold
- **THEN** the test SHALL be marked as `pytest.skip` with a descriptive reason
- **THEN** the test SHALL NOT fail

### Requirement: Batch query decomposition probes SHALL verify auto-chunking behavior across quarterly date ranges
All date-range probes SHALL use a minimum span of **1 quarter (90 days)** to reflect realistic production query patterns. Tests SHALL verify that the batch engine correctly decomposes and merges results at increasing scales.

#### Scenario: One-quarter date range (90 days, ~9 chunks)
- **WHEN** a query is sent with a 90-day date range
- **THEN** the response SHALL succeed (via async path for production-history and yield-alert)
- **THEN** the batch engine SHALL decompose into approximately 9 chunks of 10 days each
- **THEN** the merged result SHALL be complete (verified by three-point row count check)

#### Scenario: Two-quarter date range (180 days, ~18 chunks)
- **WHEN** a query is sent with a 180-day date range
- **THEN** the response SHALL succeed without timeout
- **THEN** the batch engine SHALL decompose into approximately 18 chunks
- **THEN** the merged result SHALL be complete

#### Scenario: One-year date range (365 days, ~37 chunks)
- **WHEN** a query is sent with a 365-day date range
- **THEN** the response SHALL succeed without timeout within the configured job timeout (1800s)
- **THEN** the merged result SHALL be complete (row count integrity verified)
- **THEN** if the dataset does not cover a full year, the test SHALL be marked `pytest.skip` with reason

#### Scenario: ID list exceeding batch threshold (1000 IDs)
- **WHEN** a query is sent with 1500 IDs
- **THEN** the system SHALL decompose into at least 2 batches
- **THEN** the final response SHALL contain merged results from all batches

### Requirement: Telemetry counter diffing SHALL detect spillover and guard events during stress runs
The `LoadCollector` SHALL capture `heavy_query_telemetry` counter snapshots before and after each stress test and report the delta.

#### Scenario: Guard rejection detected during stress run
- **WHEN** the `guard_reject_total` counter increases during a stress test
- **THEN** the load report SHALL include a line: "Guard rejections during test: N"
- **THEN** the specific guard type (memory, rate-limit) SHALL be identified if available

#### Scenario: Spillover events detected during stress run
- **WHEN** the `async_fallback_total` or spool write counter increases during a stress test
- **THEN** the load report SHALL include a line: "Spillover events during test: N"

#### Scenario: No telemetry events during stress run
- **WHEN** all telemetry counters remain unchanged during a stress test
- **THEN** the load report SHALL include: "No guard/spillover events detected"

#### Scenario: Telemetry endpoint unavailable
- **WHEN** the admin telemetry endpoint is unreachable
- **THEN** telemetry diffing SHALL be skipped
- **THEN** the load report SHALL note: "Telemetry unavailable -- counter diffing skipped"

### Requirement: Chunk boundary probe results SHALL be included in the session report
The `pytest_terminal_summary` hook SHALL include a "Chunk Boundary Summary" section listing each boundary probe result.

#### Scenario: All boundary probes pass
- **WHEN** all chunk boundary tests pass
- **THEN** the summary SHALL list each boundary with status "OK" and the observed behavior

#### Scenario: Boundary probe detects unexpected error
- **WHEN** a boundary probe receives an unexpected HTTP status (e.g., 500 instead of 413)
- **THEN** the summary SHALL flag that boundary as "UNEXPECTED" with the actual status code
