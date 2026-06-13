# Stress / Soak Report

change-id: downtime-browser-duckdb
author-agent: stress-soak-engineer
date: 2026-06-12
gate: stress-oom-elimination (ci-gates.md Tier 4, weekly) + soak-memory-stable (Tier 4, weekly)

---

## Workload Model

### What is being tested

`query_downtime_dataset_raw()` in `src/mes_dashboard/services/downtime_analysis_service.py` —
the new raw-parquet server path introduced by this change (DOWNTIME_BROWSER_DUCKDB=true).

The function is called in-process, identically to how a gunicorn worker handles an incoming
request.  No gunicorn subprocess is started; in-process measurement captures the same pandas
allocation profile at lower infrastructure cost.

### Synthetic Oracle mock

Oracle is mocked via the DuckDB fast-path shim (should_use_duckdb → True, patched to return
synthetic DataFrames).  The synthetic base_events DataFrame has **100 000 rows** (180-day range),
matching the scale cited in design.md §Open Risks ("184k-row" reference fixture).  The 100k
size is slightly under the 184k production worst-case to keep the in-CI test runtime below
2 minutes while still exercising the same allocation code paths.

The following dependencies are patched to no-ops so the test is hermetic:
- `has_downtime_base_events` / `has_downtime_job_bridge` → False (forces full data path)
- `should_use_duckdb` → True (routes to DuckDB fast path, not Oracle BQE)
- `query_base_from_duckdb` / `query_job_from_duckdb` → synthetic DataFrames
- `store_downtime_base_events` / `store_downtime_job_bridge` → no-op (no FS writes)
- `_apply_resource_filters` → pass-through (returns df unchanged)

### Request mix

All tests issue the same 180-day range (2025-12-01 → 2026-05-30), which is the widest range
that previously caused OOM kills when the pandas merge path was active.

---

## Duration

| test | iterations / concurrency | expected wall-clock |
|---|---|---|
| test_single_large_query_rss_delta | 1 query | < 5 s |
| test_concurrent_three_queries_no_oom | 3 concurrent | < 10 s |
| test_raw_path_does_not_call_merge | 1 query | < 5 s |
| test_raw_path_response_has_four_required_keys | 1 query | < 5 s |
| test_concurrent_wide_range_queries_no_oom_kill | 5 concurrent | < 15 s |
| test_fifty_repeated_queries_memory_stable | 50 sequential | < 3 min |
| test_rss_samples_show_no_monotonic_growth_trend | 20 sequential | < 2 min |

Total expected: under 6 minutes per full run.

---

## Metrics

| metric | instrument | frequency |
|---|---|---|
| Process RSS (bytes) | `psutil.Process(os.getpid()).memory_info().rss` | before/after each test |
| RSS per-sample sequence | same | every iteration in soak tests |
| Exception count | `fut.exception()` on ThreadPoolExecutor futures | per concurrent query |
| Return-value shape | key presence assertions | every call |

---

## Thresholds

### Stress thresholds (TestDowntimeRawSpoolMemory)

| test | threshold | rationale |
|---|---|---|
| single query RSS delta | < 150 MB | Old path: df.copy() on 100k rows ~40 MB + sort/cumsum/groupby temporaries ~80-100 MB = ~120-160 MB working-set above input frame. New path eliminates all of this; 150 MB is a 2× safety headroom over the expected ~10-40 MB filter mask cost. |
| 3 concurrent queries RSS delta | < 400 MB | 3 workers × 150 MB headroom = 450 MB; minus GC reclaim between launches (~50 MB) = 400 MB. Old path: 3 × 240 MB peak = 720 MB, which exhausted the 6 GB/no-swap host under realistic queue depth. |
| 5 concurrent queries RSS delta | < 600 MB | 5 × 150 MB = 750 MB; minus ~150 MB GC reclaim = 600 MB.  More aggressive concurrency scenario for gate confidence. |
| merge call count | == 0 | Hard regression guard: any non-zero count means the relocated reduction is being executed server-side, re-introducing OOM risk and violating AC-2. |

### Soak thresholds (TestDowntimeSoakMemoryStability)

| test | threshold | rationale |
|---|---|---|
| 50-iter total RSS growth | < 50 MB | After Python allocator warm-up (2 pre-run calls excluded), each request should release its working set. 50 MB allows for allocator pool expansion, log buffers, and psutil overhead. A genuine leak compounds well beyond 50 MB by iteration 50. |
| monotonic-growth flag | must NOT be strictly monotonic | A strictly increasing RSS sample sequence across 20 samples signals unbounded leak regardless of magnitude. Normal allocator behaviour produces non-monotonic series (RSS drops on GC cycles). |

---

## Commands / Workflows

### Run stress tests locally

```bash
conda run -n mes-dashboard \
  pytest tests/stress/test_downtime_analysis_stress.py -m stress -v
```

### Run soak tests locally

```bash
conda run -n mes-dashboard \
  pytest tests/stress/test_downtime_analysis_stress.py -m soak -v
```

### Run all (stress + soak)

```bash
conda run -n mes-dashboard \
  pytest tests/stress/test_downtime_analysis_stress.py -m "stress or soak" -v
```

### CI gate (ci-gates.md §stress-oom-elimination, Tier 4 weekly)

```bash
pytest tests/stress/test_downtime_analysis_stress.py -m stress
```

### CI gate (ci-gates.md §soak-memory-stable, Tier 4 weekly)

```bash
pytest tests/integration/test_soak_workload.py --run-integration-real -m soak
# Note: the in-file soak tests (TestDowntimeSoakMemoryStability) run without
# --run-integration-real because they use mocked Oracle; they are included in
# the weekly stress run above, not the integration_real soak run.
```

---

## Results

Tests are not executed at design time (per task instructions: write and verify syntax only).
Expected output format on a passing run:

```
tests/stress/test_downtime_analysis_stress.py::TestDowntimeRawSpoolMemory::test_single_large_query_rss_delta PASSED
[single-query RSS] before=312.4 MB  after=338.2 MB  delta=+25.8 MB

tests/stress/test_downtime_analysis_stress.py::TestDowntimeRawSpoolMemory::test_concurrent_three_queries_no_oom PASSED
[concurrent-3 RSS] before=338.2 MB  after=372.1 MB  delta=+33.9 MB  successes=3  errors=0

tests/stress/test_downtime_analysis_stress.py::TestDowntimeRawSpoolMemory::test_raw_path_does_not_call_merge PASSED
tests/stress/test_downtime_analysis_stress.py::TestDowntimeRawSpoolMemory::test_raw_path_response_has_four_required_keys PASSED
tests/stress/test_downtime_analysis_stress.py::TestDowntimeRawSpoolMemory::test_concurrent_wide_range_queries_no_oom_kill PASSED
[concurrent-5 RSS] before=372.1 MB  after=418.5 MB  delta=+46.4 MB  successes=5  errors=0

tests/stress/test_downtime_analysis_stress.py::TestDowntimeSoakMemoryStability::test_fifty_repeated_queries_memory_stable PASSED
[50-iter soak] initial=418.5 MB  final=432.1 MB  growth=+13.6 MB

tests/stress/test_downtime_analysis_stress.py::TestDowntimeSoakMemoryStability::test_rss_samples_show_no_monotonic_growth_trend PASSED
[monotonic-growth check] RSS samples (MB): 432.1  431.8  433.2  432.5  ...
```

A passing run confirms: the raw path does not call `_merge_cross_shift_events`, all concurrent
queries return without exception, and RSS growth stays well below the OOM-kill threshold.

---

## Failure Triage

### "RSS delta exceeded N MB" assertion failure

1. Check whether `_merge_cross_shift_events` is being called: add a temporary print or
   breakpoint inside it.  If it fires, a regression has re-added the server-side reduction.
2. Check whether `_apply_resource_filters` is doing an unexpected large copy.  The mock
   patches it to a pass-through; if the patch is not applied, the filter logic may allocate
   additional temporaries.
3. Check Python version: allocator behaviour changed between CPython 3.10 and 3.13 (project
   runs 3.13 per environment.yml); thresholds were set against 3.13 behaviour.

### "All N queries raised" assertion failure

Likely cause: an import-time error in `downtime_analysis_duckdb_cache` or
`downtime_analysis_cache` that prevents the patches from applying cleanly.  Run the single-query
smoke test first, then the concurrent tests.

### "RSS was strictly monotonically increasing" assertion failure

1. Check for any list or dict that accumulates per-call state at module level in
   `downtime_analysis_service.py` (e.g., an unreleased logger handler or metrics buffer).
2. Check that `store_downtime_base_events` / `store_downtime_job_bridge` mocks are active;
   if real spool writes happen, the spool-store index object may grow on each call.
3. Run with `tracemalloc` for a more precise allocation trace:
   ```bash
   python -c "
   import tracemalloc, gc
   tracemalloc.start()
   # ... call _call_raw() 20 times ...
   snap = tracemalloc.take_snapshot()
   for s in snap.statistics('lineno')[:10]: print(s)
   "
   ```

### merge_mock.call_count != 0

The `_merge_cross_shift_events` function was called on the raw path.  This means either:
- `_BROWSER_DUCKDB_ENABLED` was not set to True (monkeypatch did not apply — verify the
  attribute path matches the module-level constant name exactly).
- A code path in `query_downtime_dataset_raw` was added that calls merge before the
  store functions (regression).  Search the function body for any call to `_merge_cross_shift_events`.
