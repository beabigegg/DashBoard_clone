## 1. Core Data Structures

- [x] 1.1 Create `tests/stress/load_collector.py` with `LoadSample` and `LoadSummary` dataclasses (fields: peak/avg CPU, peak/avg memory, peak DB pool, per-queue RQ depth for 5 queues, sample_count, null_sample_count, duration_sec)
- [x] 1.2 Implement `LoadSummary.assert_within(max_cpu_pct, max_mem_pct, max_db_pool_pct)` — raises `AssertionError` with metric details on breach, skips `None` metrics

## 2. LoadCollector Implementation

- [x] 2.1 Implement `LoadCollector` context manager with daemon sampling thread that polls `GET {base_url}/health` at configurable interval
- [x] 2.2 Parse `/health` response to extract `system_memory.used_pct`, `system_memory.available_mb`, `system_memory.pressure` and CPU fields into `LoadSample`
- [x] 2.3 Add optional `/admin/api/performance-detail` polling for DB pool utilization (`db_pool_active`, `db_pool_size`) and per-queue RQ depth (5 queues: trace-events, reject-query, msd-analysis, production-history-query, yield-alert-query) — gracefully skip if unavailable
- [x] 2.4 Implement graceful error handling: record null samples on connection failure, stop thread within one interval on context exit

## 3. StressTestResult Integration

- [x] 3.1 Add optional `load_summary: Optional[LoadSummary] = None` field to `StressTestResult` in `tests/stress/conftest.py`
- [x] 3.2 Extend `StressTestResult.report()` to append "System Load" section when `load_summary` is present (peak CPU %, peak mem %, avg CPU %, avg mem %, peak DB pool % or N/A, sample count)

## 4. Pytest Fixtures and Hooks

- [x] 4.1 Add `load_collector_factory` session-scoped fixture returning a callable `(base_url, interval) -> LoadCollector`
- [x] 4.2 Add `load_collector` function-scoped fixture using `base_url` from config and interval from `STRESS_LOAD_INTERVAL` env (default 2.0)
- [x] 4.3 Implement `pytest_terminal_summary` hook to emit consolidated "Load Monitoring Summary" table across all tests that recorded a `LoadSummary`

## 5. Orchestrator Integration

- [x] 5.1 Add `--load-monitor` flag to `scripts/run_stress_tests.py`
- [x] 5.2 Set `STRESS_LOAD_MONITORING=1` in env when `--heavy` or `--load-monitor` is used; do not set for `--quick`

## 6. Threshold Assertions in Existing Tests

- [x] 6.1 Add load monitoring opt-in to `test_api_load.py` — wrap heavy concurrent tests with `LoadCollector`, call `assert_within()` when `STRESS_LOAD_MONITORING=1`
- [x] 6.2 Add configurable threshold env vars: `STRESS_MAX_MEM_PCT` (default 85), `STRESS_MAX_DB_POOL_PCT` (default 90), `STRESS_MAX_GUARD_REJECTS` (default 5), `STRESS_MAX_QUEUE_DEPTH` (default 20)

## 7. Telemetry Counter Diffing

- [x] 7.1 Extend `LoadCollector` to snapshot `heavy_query_telemetry` counters (guard_reject_total, async_fallback_total, memory_error_total, spool cache hit/miss) from `/admin/api/performance-detail` at start and end of collection
- [x] 7.2 Add `TelemetryDiff` dataclass with fields for each counter delta; attach to `LoadSummary` as optional `telemetry_diff`
- [x] 7.3 Include telemetry diff in `StressTestResult.report()` — show guard rejections, spillover events, memory errors; show "No guard/spillover events detected" when all zeros

## 8. Chunk Boundary Probe Tests

- [x] 8.1 Create `tests/stress/test_chunk_boundary.py` with parameterized request payload boundary probes: JSON body (200KB/255KB/300KB), container ID batch (150/200/250), resource detail limit (400/500/600)
- [x] 8.2 Add result spillover boundary probes: queries targeting ~100K rows (below), ~190K rows (near), ~250K rows (above spillover threshold) — skip if dataset insufficient
- [x] 8.3 Add batch decomposition probes using minimum 1-quarter date ranges: 90-day (~9 chunks), 180-day (~18 chunks), 365-day (~37 chunks, skip if data unavailable); 800-ID vs 1500-ID list — verify auto-chunking and merge succeed without timeout
- [x] 8.4 Add chunk boundary summary to `pytest_terminal_summary` — list each boundary with OK/UNEXPECTED status

## 9. Data Integrity Probe Infrastructure

- [x] 9.1 Create `tests/stress/integrity_helpers.py` with `RowCountBaseline` helper — executes COUNT(*) via a lightweight API or direct DB query, stores expected row count per service/filter combo
- [x] 9.2 Implement `PaginationWalker` helper — walks all pages of a spooled result, sums row counts, detects empty/error pages mid-traversal (use page_size=500 for efficiency)
- [x] 9.3 Implement `IntegrityResult` dataclass — holds baseline_count, api_total_rows, pagination_sum, deficit_pct, verdict (PASS/FAIL/SKIPPED), checkpoint_failed
- [x] 9.4 Add configurable tolerance env var `STRESS_ROW_COUNT_TOLERANCE_PCT` (default 0.1%)

## 10. Data Integrity Probe Tests Per Service

- [x] 10.1 Create `tests/stress/test_data_integrity.py` with reject-history batch merge probes — 90-day (1 quarter, ~9 chunks) and 365-day (1 year, ~37 chunks, skip if unavailable) queries; COUNT baseline, three-point verification, partial_failure metadata check
- [x] 10.2 Add reject-history ID-batch merge probe — 1500 lot IDs, verify merged result count matches baseline
- [x] 10.3 Add production-history truncation detection probes via async path — 90-day baseline integrity probe + 365-day near-truncation probe (skip if unavailable); compare against COUNT baseline, detect silent truncation, verify failed async jobs don't leave partial spool
- [x] 10.4 Add hold-history pagination integrity probe — query >5000 rows, walk all pages, verify sum == total_rows
- [x] 10.5 Add query-tool ID merge probe — 1500 container IDs, cross-reference result IDs against input list to detect missing entries
- [x] 10.6 Add yield-alert concurrent integrity probe — 3 concurrent queries at slot limit via async path, each verified with three-point check
- [x] 10.7 Add data integrity summary to `pytest_terminal_summary` — per-service OK/DATA LOSS/SKIPPED with row counts and deficit %

## 11. Async Job Stress Probes

- [x] 11.1 Create `tests/stress/async_helpers.py` with `AsyncJobPoller` class — handles 200 (spool hit) and 202 (polling loop) paths, configurable `max_wait` and `poll_interval`, raises `AsyncJobTimeout` on timeout
- [x] 11.2 Create `tests/stress/test_async_job_stress.py` with queue saturation probe — submit 5 concurrent production-history queries, verify all complete, record peak queue depth
- [x] 11.3 Add yield-alert queue saturation probe — submit 5 concurrent yield-alert queries, verify no job silently dropped
- [x] 11.4 Add polling concurrency probe — 10 threads poll same job_id simultaneously, verify consistent responses and no 500 errors
- [x] 11.5 Add spool hit bypass probe — submit same production-history query twice, verify second gets HTTP 200; submit 5 identical queries concurrently, verify at most 1 RQ job created
- [x] 11.6 Add retry behavior verification — check RQ failed queue after stress run, verify no job exceeded max 3 attempts (initial + 2 retries)

## 12. Tests for Load Collector, Chunk Probes, and Integrity Helpers

- [x] 12.1 Unit test `LoadSummary.assert_within()` — passing case, breach case, None-skip case
- [x] 12.2 Unit test `LoadCollector` with mock HTTP responses — valid samples, connection failures, mixed samples, RQ queue depth parsing
- [x] 12.3 Unit test `TelemetryDiff` computation — counter increase, counter unchanged, endpoint unavailable
- [x] 12.4 Unit test `StressTestResult.report()` with load_summary, telemetry_diff, and integrity results
- [x] 12.5 Unit test chunk boundary probe helpers — payload generation at size boundaries
- [x] 12.6 Unit test `PaginationWalker` — complete walkthrough, mid-pagination error, empty page detection
- [x] 12.7 Unit test `IntegrityResult` verdict logic — within tolerance (PASS), over tolerance (FAIL), baseline unavailable (fallback to two-point)
- [x] 12.8 Unit test `AsyncJobPoller` — sync 200 path, async 202 polling path, job failure, timeout
