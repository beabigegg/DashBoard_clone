## Why

Current stress tests (`tests/stress/`) measure endpoint success rates and response times, but do not capture **system-level resource consumption** (CPU, memory, disk I/O, DB connection pool) during high-concurrency heavy-query runs. When a stress test passes its 95% success-rate threshold but the server is at 90% memory or saturating DB connections, operators have no visibility into the headroom gap.

Additionally, the system has **multiple chunk/size limit boundaries** (256 KB request body, 200 container ID batch, 48 MB / 200K-row result spillover, 192 MB per-chunk memory guard, 10.7 GB spool disk) but no automated tests verify whether realistic high-concurrency workloads actually trigger these limits. Silent spillovers or guard rejections during load may degrade user experience without surfacing as test failures.

More critically, batch query merging has **multiple silent data loss paths** — schema mismatch causes entire chunks to be skipped (`continue`), overflow mode defaults to `truncate`, partial chunk failures return incomplete results without clear user notification, and spool TTL expiration mid-pagination silently returns empty data. None of these are tested.

Furthermore, production-history and yield-alert queries have been **offloaded to dedicated RQ async workers** (commit dfa7483), changing the API contract from synchronous blocking to `202 ACCEPTED → polling → spool hit`. The system now runs **5 RQ workers** (trace, reject, msd, production-history, yield-alert) with isolated DB pools (`DB_POOL_SIZE=2, MAX_OVERFLOW=1` each). Existing stress tests do not account for this async polling pattern, queue depth monitoring, retry storms, or the increased baseline memory footprint (~5 workers × 200MB).

Adding runtime load monitoring, chunk boundary detection, **data integrity verification, and async job lifecycle testing** to stress tests lets us detect resource exhaustion risks, size-limit edge cases, silent data loss, and async pipeline failures before they manifest as production incidents.

## What Changes

- Add a **system load collector** that samples CPU %, memory %, DB connection pool utilization, and **per-queue RQ depth** (5 queues: trace, reject, msd, production-history-query, yield-alert-query) at configurable intervals during stress test execution.
- Extend `StressTestResult` with load monitoring summary fields (peak CPU, peak memory, peak DB pool usage, avg queue depth).
- Add **threshold assertions** for system load — stress tests can fail not only on success rate but also on resource exhaustion signals (e.g., peak memory > 85%, DB pool saturation > 90%).
- Generate a **load monitoring report** at the end of each stress test run, summarizing time-series system metrics alongside the existing per-endpoint results.
- Integrate with the existing `run_stress_tests.py` orchestrator so load collection activates automatically for `--heavy` mode and optionally for other modes.
- Add a **chunk boundary probe** that exercises requests near the edge of each size limit (request body 256 KB, container ID batch 200, result sets near spillover thresholds) and verifies whether the system handles them gracefully (proper HTTP status, spillover activation, no unhandled errors).
- Detect and report **silent spillover events** (result → Parquet, spool disk growth) and **guard rejections** (memory guard, rate limit) that occur during stress runs, surfacing them in the test report.
- Add **data integrity probes** that verify row count consistency across the batch-merge → spool → pagination pipeline: pre-query COUNT(*) vs API total_rows, spool registration vs actual Parquet row count, and full pagination sum vs declared total.
- Add **async job lifecycle probes** for production-history and yield-alert: verify 202 → polling → completed flow, test concurrent job submission against queue capacity, detect job timeout/retry storms under load, and verify data integrity through the async pipeline (job enqueue → RQ execution → spool write → client retrieval).

## Capabilities

### New Capabilities
- `stress-test-load-collector`: System resource sampling during stress test execution (CPU, memory, DB pool, RQ queue depth) with configurable interval and threshold assertions.
- `stress-test-load-report`: Post-run load monitoring report generation summarizing peak/avg system metrics alongside endpoint performance results.
- `chunk-boundary-probe`: Boundary tests that exercise request payload limits (256 KB JSON, 200 container IDs, 500 resource detail), result spillover thresholds (48 MB / 200K rows), batch query decomposition (10-day / 1000-ID), and per-chunk memory guards (192 MB) — verifying correct HTTP status codes, graceful spillover, and absence of unhandled errors.
- `data-integrity-probe`: Row count integrity verification across the query pipeline — pre-query COUNT(*) vs API response total_rows, batch merge completeness, spool write/read row count consistency, and full pagination walkthrough to detect silent truncation or chunk loss.
- `async-job-stress-probe`: Async job lifecycle testing under load — concurrent job submission, queue depth saturation, polling latency, job timeout detection, retry storm detection, and end-to-end data integrity through the async pipeline for production-history and yield-alert workers.

### Modified Capabilities
- `stress-test-coverage`: Extend stress test requirements to include system load threshold assertions (peak memory, DB pool saturation), chunk boundary validation, and data integrity checks as pass/fail criteria.

## Impact

- **Tests**: `tests/stress/conftest.py` (StressTestResult extension, new fixtures), all `tests/stress/test_*.py` files (opt-in load assertions), new `tests/stress/test_chunk_boundary.py`, `scripts/run_stress_tests.py` (orchestrator integration).
- **Config read (no modify)**: `config/settings.py` (reads MAX_JSON_BODY_BYTES, QUERY_TOOL_MAX_CONTAINER_IDS, etc.), `services/reject_dataset_cache.py` (reads spillover thresholds), `services/batch_query_engine.py` (reads chunk config).
- **Dependencies**: `psutil` (already used by `system-memory-monitoring`), no new external dependencies.
- **Services under integrity test**: `reject_dataset_cache` (batch merge + spillover), `production_history_service` (batch merge + truncation + **async job lifecycle**), `yield_alert_dataset_cache` (spool lifecycle + **async job lifecycle**), `hold_dataset_cache` (spool pagination), `query_spool_store` (TTL expiration, column hash validation).
- **RQ infrastructure**: 5 queues monitored (`production-history-query`, `yield-alert-query`, `trace-events`, `reject-query`, `msd-analysis`), worker process isolation validated, Redis control-plane pressure checked.
- **No production code changes** — this is purely test infrastructure.
