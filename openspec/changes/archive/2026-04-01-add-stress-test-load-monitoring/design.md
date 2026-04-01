## Context

The stress test suite (`tests/stress/`) uses `concurrent.futures` to generate load against API endpoints and collects per-request metrics (success rate, response times, RPS) via the `StressTestResult` dataclass. However, there is no visibility into what happens on the **server side** during these runs — CPU saturation, memory pressure, DB connection pool exhaustion, or RQ queue buildup are all invisible. The `system-memory-monitoring` spec already ensures `/health` exposes `system_memory` data, and `core/metrics.py` tracks query latency percentiles, but none of this is consumed by the stress test harness.

As of commit dfa7483, production-history and yield-alert queries are now offloaded to **dedicated RQ async workers** (`production-history-query` and `yield-alert-query` queues). The API contract changed from synchronous blocking to `202 ACCEPTED → polling → spool hit`. The system now runs 5 RQ workers total, each with isolated DB pools (`DB_POOL_SIZE=2, MAX_OVERFLOW=1`). Existing stress tests assume synchronous responses and do not exercise the async polling loop, queue depth monitoring, or the new failure modes (job timeout at 1800s, auto-retry with `[30, 60]` intervals).

## Goals / Non-Goals

**Goals:**
- Collect system resource metrics (CPU, memory, DB pool, RQ queue) during stress test execution via a background sampling thread.
- Surface peak/average system load alongside per-endpoint results in `StressTestResult.report()`.
- Allow stress tests to assert on system load thresholds (e.g., "peak memory must not exceed 85%").
- Generate a consolidated load monitoring report after each stress test run.
- Integrate seamlessly with the existing `run_stress_tests.py` orchestrator.
- **Probe chunk/size boundaries** — send requests near the edge of each size limit and verify the system responds correctly (proper HTTP status, graceful spillover, no crashes).
- **Detect silent spillover/rejection events** during stress runs — surface guard rejections, result-to-Parquet spillovers, and spool disk growth in the test report.
- **Verify data integrity across the query pipeline** — confirm row counts are preserved through batch decomposition → chunk merge → spool write → pagination read, detecting silent truncation, chunk skipping, and partial failure scenarios.

**Non-Goals:**
- Real-time dashboarding or live streaming of metrics during tests.
- Modifying production application code — all changes are in test infrastructure.
- Replacing or duplicating the existing `core/metrics.py` / `metrics_history.py` — we consume their data, not rebuild it.
- Supporting distributed load generation (multi-machine); this is single-host collection.
- Changing any chunk size limits — we only detect and report, never modify thresholds.

## Decisions

### D1: Collect metrics via `/health` and `/admin/api/performance-detail` polling

**Choice:** Sample system metrics by polling the application's own health and admin endpoints from a background thread in the test process.

**Alternatives considered:**
- **SSH/psutil on the server directly** — requires the test process to run on the same host or have SSH access; breaks when testing remote targets.
- **Prometheus scraping** — adds infrastructure dependency not present today; overkill for test-time collection.
- **In-process hooks** — would require production code changes, violating the non-goal.

**Rationale:** The `/health` endpoint already exposes `system_memory` (per `system-memory-monitoring` spec). The `/admin/api/performance-detail` endpoint exposes DB pool stats and process cache info. Polling these from the test process is zero-dependency and works regardless of deployment topology.

### D2: Implement as a context-manager `LoadCollector` class

**Choice:** A `LoadCollector` context manager that starts a daemon thread on `__enter__`, samples at a configurable interval (default 2s), and stops + returns a `LoadSummary` summary on `__exit__`.

```python
with LoadCollector(base_url, interval=2.0) as collector:
    # run stress test
    ...
load_summary = collector.summary  # LoadSummary dataclass
```

**Rationale:** Context-manager pattern ensures the sampling thread is always cleaned up. Returning a summary dataclass keeps the API consistent with the existing `StressTestResult` pattern.

### D3: Extend `StressTestResult` with an optional `load_summary` field

**Choice:** Add an optional `load_summary: Optional[LoadSummary]` field to `StressTestResult`. When present, `report()` appends a "System Load" section.

**Rationale:** Backward-compatible — existing tests that don't use load monitoring are unaffected. The report extension is additive.

### D4: Provide a `load_collector` pytest fixture

**Choice:** A session-scoped `load_collector_factory` fixture that creates `LoadCollector` instances, plus a function-scoped `load_collector` fixture for per-test usage.

**Rationale:** Follows the existing pattern of `stress_result` factory fixture. Session-scoped factory avoids repeated initialization overhead.

### D5: Threshold assertions via `LoadSummary.assert_within()`

**Choice:** `LoadSummary` provides an `assert_within(max_cpu_pct, max_mem_pct, max_db_pool_pct)` method that raises `AssertionError` with details when any threshold is breached.

**Rationale:** Keeps assertion logic co-located with the data. Tests call `load_summary.assert_within(cpu=90, mem=85, db_pool=90)` for readable threshold checks.

### D6: Report generation as a pytest plugin hook

**Choice:** Use `pytest_terminal_summary` hook to emit a consolidated load monitoring report at the end of the test session, collecting all `LoadSummary` instances from the session.

**Rationale:** Non-invasive — doesn't require changes to individual test files. The report is automatically appended to the pytest output.

### D7: Chunk boundary probes as a dedicated test module

**Choice:** Create `tests/stress/test_chunk_boundary.py` with parameterized tests that exercise each size limit boundary. Each probe sends requests at three levels: **below limit** (should succeed), **at limit** (should succeed), and **above limit** (should return proper error/spillover).

**Boundaries to probe:**

| Boundary | Light | Medium | Heavy | Expected behavior |
|---|---|---|---|---|
| JSON body (256 KB) | 200 KB payload | 255 KB payload | 300 KB payload | HTTP 413 above limit |
| Container ID batch (200) | 150 IDs | 200 IDs | 250 IDs | HTTP 413 above limit |
| Resource detail limit (500) | 400 records | 500 records | 600 records | HTTP 413 above limit |
| Result spillover (48 MB / 200K rows) | Query returning ~100K rows | ~190K rows | ~250K rows | Parquet spillover, no error |
| Batch time decomposition | 1 quarter (90 days, ~9 chunks) | 2 quarters (180 days, ~18 chunks) | 1 year (365 days, ~37 chunks) | Auto-decomposed, merged, no timeout |
| Batch ID threshold (1000) | 800 IDs | 1000 IDs | 1500 IDs | Auto-decomposed into batches |

**Note on date range minimum:** All date-range probes use a minimum span of **1 quarter (90 days)**. Sub-quarter ranges are not tested because they fall within a single batch chunk (10-day threshold) and do not exercise the decomposition and merge logic under real production query patterns.

**Alternatives considered:**
- **Fuzz random payloads** — less deterministic, harder to assert on. Boundary probes are more targeted.
- **Mock the limits** — defeats the purpose; we need to verify the real production guards.

**Rationale:** Parameterized boundary tests give clear pass/fail signals per limit. The three-level approach (below/at/above) confirms both the happy path and the guard behavior.

### D8: Detect spillover events via telemetry endpoint polling

**Choice:** During stress runs, poll `/admin/api/performance-detail` (already polled for DB pool in D1) and extract `heavy_query_telemetry` counters: `guard_reject_total`, `async_fallback_total`, `spool_cache_hit/miss`, and `memory_error_total`. Diff the counters before and after a stress test to detect events that occurred during the run.

**Rationale:** The telemetry counters already exist in `core/heavy_query_telemetry.py`. Polling the admin endpoint captures them without production code changes. Counter diffs give exact event counts during each test.

### D9: Row count integrity verification via pre-query COUNT(*) baseline

**Choice:** For each data integrity probe, first execute a lightweight `COUNT(*)` query with the same filters to establish the **expected row count**, then execute the actual API query and compare `response.total_rows` against the baseline.

**Verification pipeline:**

```
COUNT(*) baseline  ──→  API query  ──→  Compare total_rows
                                    ──→  Paginate all pages  ──→  sum(page_rows) == total_rows
                                    ──→  If spool: verify spool metadata row count
```

**Three-point verification:**
1. **Baseline vs API**: `COUNT(*)` result == `response.total_rows` (detects batch merge loss, chunk skipping, silent truncation)
2. **API vs Pagination**: `total_rows` == `sum(rows across all pages)` (detects spool TTL expiration, pagination gaps)
3. **Spool metadata vs file**: `registered_row_count` == actual Parquet row count (detects write corruption)

**Alternatives considered:**
- **Checksum-based verification** — comparing row-level checksums would detect column-level corruption but is too expensive for stress test runs and requires DB-side checksum support.
- **Sample-based spot-checking** — verifying random rows exist is weaker than full count verification and still requires a baseline.

**Rationale:** Row count is the cheapest integrity signal that catches the most common failure modes (truncation, chunk skip, partial failure). The three-point approach narrows down exactly where in the pipeline data was lost.

### D10: Targeted service coverage for integrity probes

**Choice:** Test data integrity across the 5 services that use the batch/spool pipeline, each targeting its specific risk:

| Service | Primary Risk | Probe Strategy |
|---|---|---|
| **Reject History** | Batch merge (time + ID decomposition), spillover at 200K rows | Large date range + multi-lot query → COUNT baseline → full pagination |
| **Production History** | `overflow_mode="truncate"` default, batch merge | Wide date range → verify no silent truncation |
| **Yield Alert** | Slow query concurrency rejection, spool lifecycle | Concurrent queries during load → verify complete results |
| **Hold History** | Spool pagination (5000-row threshold) | Query > 5000 rows → paginate all → verify sum |
| **Query Tool** | ID batch decomposition (1000-ID threshold) | >1000 container IDs → verify merged result count |

**Rationale:** Each service has a different dominant risk path. Testing them individually ensures we catch service-specific issues rather than assuming one pattern covers all.

### D11: Async job polling helper for stress tests

**Choice:** Create an `AsyncJobPoller` helper in `tests/stress/async_helpers.py` that encapsulates the 202 → polling → result retrieval pattern used by production-history and yield-alert.

```python
poller = AsyncJobPoller(base_url, max_wait=300, poll_interval=2.0)
result = poller.submit_and_wait("POST", "/api/production-history/query", params)
# result.job_id, result.status, result.elapsed, result.poll_count, result.data
```

**Behavior:**
- On HTTP 200 (spool hit): returns immediately with sync result
- On HTTP 202: extracts `job_id` + `status_url`, polls until `status="completed"` or timeout
- On job failure: returns error details from polling response
- On timeout: raises `AsyncJobTimeout` with job_id and elapsed time

**Rationale:** Both production-history and yield-alert use identical polling patterns. A shared helper avoids duplicating the poll loop in every test and provides uniform timeout/error handling.

### D12: RQ queue depth monitoring via `/admin/api/rq-status`

**Choice:** Extend `LoadCollector` to sample per-queue RQ depth from the admin endpoint. The 5 monitored queues are: `trace-events`, `reject-query`, `msd-analysis`, `production-history-query`, `yield-alert-query`.

**Metrics captured per sample:**
- `queue_depth` — number of enqueued jobs waiting
- `started_count` — jobs currently executing
- `failed_count` — jobs that failed since last snapshot

**Rationale:** Queue depth is the primary indicator of async backpressure. If production-history-query depth exceeds the worker's processing rate, jobs queue up and user-perceived latency grows even though the API returns 202 instantly.

### D13: Partial failure detection via response metadata inspection

**Choice:** After each heavy query, inspect the API response for `partial_failure` or `has_partial_failure` metadata. If present, the test records it as a **data integrity warning** (not immediate failure) and verifies the row count deficit matches the declared missing chunk count.

**Rationale:** The batch engine already tracks partial failures in progress metadata. The integrity probe confirms this metadata is (a) actually surfaced to the API response and (b) accurate about how many rows were lost.

### D14: Async-specific stress scenarios

**Choice:** Add dedicated stress scenarios for the async pipeline:

| Scenario | Method | What it tests |
|---|---|---|
| **Queue saturation** | Submit N concurrent production-history queries (N > 1 worker) | Jobs queue correctly, no jobs lost |
| **Polling storm** | 10 clients poll same job_id simultaneously | Polling endpoint handles concurrent reads |
| **Job timeout** | Submit query with very large date range (> 3 years) | 1800s timeout fires, job marked failed, client gets error |
| **Retry storm** | Trigger job failure (e.g., DB connection timeout) | Max 2 retries with [30, 60]s intervals, no infinite loop |
| **Spool hit bypass** | Submit same query twice | Second request gets 200 (spool hit), not 202 |
| **RQ unavailable fallback** | Disable RQ worker, submit query | Returns 503 or falls back to sync |

**Rationale:** The async path introduces failure modes invisible to synchronous stress tests — queue backpressure, polling overhead, retry storms, and stale job metadata.

## Risks / Trade-offs

- **Polling overhead** — Sampling `/health` every 2s adds trivial load (<1 req/2s), but could slightly skew results for tests with very low concurrency. → Mitigation: disable load collection in `--quick` mode; 2s interval is coarse enough to be negligible.
- **Endpoint availability** — `/health` and `/admin/api/performance-detail` must be accessible from the test client. → Mitigation: `LoadCollector` gracefully handles connection errors, recording `null` samples without failing the test.
- **Metric granularity** — 2s sampling interval may miss sub-second spikes. → Mitigation: acceptable for stress tests which run for 10s–60s+; for sub-second analysis, production telemetry (metrics_history) is the right tool.
- **Admin endpoint auth** — `/admin/api/performance-detail` may require auth in some deployments. → Mitigation: `LoadCollector` treats admin metrics as optional; core functionality (CPU/memory via `/health`) works without admin access.
- **Boundary probe data setup** — Probing result spillover (200K+ rows) requires queries that actually return that volume. → Mitigation: use date range manipulation to control result size; tests that can't hit the threshold in the current dataset are marked `skip` with a reason, not `fail`.
- **Spillover detection relies on telemetry counters** — If `heavy_query_telemetry` counters are reset (e.g., worker restart during test), diffs may undercount. → Mitigation: record counter snapshots at test boundaries; document this limitation in the report.
- **COUNT(*) baseline may not match API rows exactly** — Concurrent inserts/deletes between COUNT and query can cause small discrepancies. → Mitigation: allow a configurable tolerance (default ±0.1%) via `STRESS_ROW_COUNT_TOLERANCE_PCT`; exact match is not the goal — detecting 10-20% loss from chunk skipping is.
- **Pagination walkthrough is slow** — Walking all pages of a 200K-row result at 100 rows/page = 2000 requests. → Mitigation: use larger page sizes (500-1000) for integrity probes; this is about counting, not rendering.
- **Spool Parquet file access** — Reading the Parquet file directly to verify row count requires the test to run on the same host as the spool directory. → Mitigation: make Parquet-level verification optional (`STRESS_VERIFY_SPOOL_FILE=0` by default); rely on metadata-level verification as the primary check.
