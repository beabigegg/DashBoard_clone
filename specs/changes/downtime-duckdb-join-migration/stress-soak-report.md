# Stress / Soak Report

**Change:** downtime-duckdb-join-migration
**Tier:** 1 (high risk — system #1 OOM risk point)
**Required by:** change-classification.md (`stress-soak-report.md: yes`)
**AC gated:** AC-5 (OOM ceiling proof)
**Risk addressed:** R2 (design.md §5 — hot single RESOURCEID candidate fan-out)

---

## Workload Model

The migration replaces `_bridge_jobid` Path B's `pd.merge(events_b, jobs_b, how='left')`
— an N×M Cartesian pre-join executed entirely in Python heap — with a DuckDB RANGE JOIN
(bridge_join.sql, ADR-0010) that spills intermediate candidates to disk.

Three workload profiles are exercised:

| profile | events | jobs | RESOURCEIDs | DuckDB memory_limit | candidate rows (O) |
|---|---|---|---|---|---|
| AC-5 baseline | 10,000 | 1,000 | 1 | 64 MB | 10M |
| AC-5 multi-resource | 500 | 200 | 50 | 64 MB | 5M total (100k per resource) |
| R2 hot-RESOURCEID | 50,000 | 5,000 | 1 | 128 MB | 250M |

All events are designed for worst-case fan-out: every job's time window overlaps every
event's time window for the same RESOURCEID.  This maximises the candidate set that the
RANGE JOIN must produce before the `ROW_NUMBER() OVER (PARTITION BY event_id ...)` winner
selection reduces it to one row per event.

No Oracle or RQ machinery is used.  The bridge JOIN is called directly via
`DowntimeJob._run_bridge_join(base_df, job_df)` with a patched `duckdb.connect` that
injects `SET memory_limit` and `SET temp_directory` before each connection.

---

## Duration

- **stress tests:** single-run, expected wall-clock per test:
  - `test_high_cardinality_join_completes_without_python_oom`: ~5–30 s (DuckDB join + spill)
  - `test_multi_resourceid_fan_out_scales_linearly`: <120 s ceiling (50 serial groups)
  - `test_single_hot_resourceid_r2`: ~60–300 s (DuckDB join at 250M candidate scale)
- **soak test (deferred):** 24-hour looping run at weekly cadence — see Deferred section.

---

## Metrics

| metric | measurement method | AC-5 baseline ceiling | R2 ceiling |
|---|---|---|---|
| Python RSS peak | `psutil.Process.memory_info().rss` after GC | < 512 MB | < 1024 MB |
| Python MemoryError | exception type | must not raise | must not raise |
| Output rowcount | `len(result_df)` | == n_events (10,000) | == n_events (50,000) |
| match_source validity | column `.unique()` | in {overlap, jobid, none} | in {overlap, jobid, none} |
| match_ambiguous type | column dtype | bool (not object/NULL) | bool (not object/NULL) |
| Wall clock (multi-resource) | `time.monotonic()` | — | n/a |
| Wall clock (50-resource fan-out) | `time.monotonic()` | — ceiling 120 s | n/a |

RSS is measured before and after the JOIN call with two `gc.collect()` passes to
reduce allocator-pool noise.  `tracemalloc` is started/stopped around the AC-5 baseline
test for supplementary Python-heap allocation evidence.

---

## Thresholds

```
test_high_cardinality_join_completes_without_python_oom (AC-5):
  - completes: no MemoryError, no subprocess crash
  - output rowcount: == 10,000
  - all events match via 'overlap' match_source (by construction)
  - peak RSS: < 512 MB

test_multi_resourceid_fan_out_scales_linearly (AC-5 fan-out):
  - all 50 groups complete without error
  - each group output rowcount: == 500
  - total wall clock: < 120 s

test_single_hot_resourceid_r2 (R2 guard):
  - completes: no MemoryError
  - output rowcount: == 50,000
  - match_ambiguous column: present, dtype bool
  - peak RSS: < 1024 MB
```

Threshold rationale:

- **512 MB AC-5:** Legacy `pd.merge` on 10k events × 1k candidates requires ~2–4 GB in-process
  (Cartesian frame before time-overlap filtering + pandas sort/copy temporaries).  512 MB
  represents the upper bound for Arrow batch loading + DuckDB connection overhead without
  the in-Python candidate explosion.
- **1024 MB R2:** At 250M candidates DuckDB itself requires headroom for the ranked window
  CTE; the threshold is set to 1 GB so that Python-side Arrow load (50k × ~200 B/row ≈
  10 MB base; 5k jobs × ~300 B ≈ 1.5 MB) plus DuckDB process memory (shared heap with
  Python in-process) stays inside the 6 GB production host with three concurrent workers
  (3 × 1 GB + 3 GB OS/other = 6 GB margin zero).
- **120 s multi-resource:** 50 serial bridge-JOIN calls at 100k candidates each; this
  exercises duckdb.connect overhead and temp-directory spill I/O.  On a 4-core CI runner
  at 2.5 GHz and NVMe temp storage the baseline should be well under 60 s; the ceiling
  is doubled to absorb I/O jitter on shared CI infrastructure.

---

## Commands / Workflows

```bash
# Weekly stress cadence (not pre-merge):
conda run -n mes-dashboard \
  pytest tests/stress/test_downtime_analysis_stress.py \
    -m stress \
    -k "OomCeiling" \
    -v \
    --tb=short \
    -p no:randomly

# Individual guards:
conda run -n mes-dashboard \
  pytest tests/stress/test_downtime_analysis_stress.py::TestDowntimeJobOomCeiling::test_high_cardinality_join_completes_without_python_oom \
    -v --tb=long

conda run -n mes-dashboard \
  pytest tests/stress/test_downtime_analysis_stress.py::TestDowntimeJobOomCeiling::test_single_hot_resourceid_r2 \
    -v --tb=long

# Optional: override DuckDB spill directory to fast NVMe in CI:
DUCKDB_JOB_DIR=/tmp/duckdb_stress \
conda run -n mes-dashboard \
  pytest tests/stress/test_downtime_analysis_stress.py -m stress -k OomCeiling -v
```

The tests are marked `@pytest.mark.stress` (registered in `pytest.ini`) and are
NOT in the pre-merge floor (collect / targeted / changed-area / contract phases).
They run only in the weekly stress cadence or via manual invocation.

---

## Results

**Status: expected / pre-run**

These tests have not yet run in CI.  The expected outcomes below are derived from:
1. DuckDB's documented IEJoin (inequality-equality join) disk-spill behaviour when
   `memory_limit` is exceeded on the intermediate build side.
2. The RSS measurement pattern already validated in `TestDowntimeRawSpoolMemory`
   (same psutil approach, same process, same GC stabilization).
3. The bridge_join.sql structure: the candidate explosion happens inside a DuckDB CTE
   (`path_b_candidates`), which DuckDB materializes in its own buffer pool — this
   buffer is what triggers spill and never lands in the Python heap.

When CI runs these tests for the first time, update this section with:
- Actual RSS measurements per test
- Wall-clock per group (multi-resource test)
- Observed match_ambiguous fraction for R2 (informational)
- Any DuckDB version-specific spill behavior notes

---

## Failure Triage

### MemoryError in test_high_cardinality_join_completes_without_python_oom

Cause: `_run_bridge_join` is still calling `pd.merge` instead of bridge_join.sql, OR
the `duckdb.connect` patch is not being applied at the correct import site.

Diagnosis:
```python
# Confirm the patch target is correct:
import mes_dashboard.workers.downtime_worker as dw
print(dw.duckdb)  # should be duckdb module
# The patch targets 'mes_dashboard.workers.downtime_worker.duckdb.connect'
```

Fix: confirm `DowntimeJob._run_bridge_join` imports `duckdb` at function scope
(not module level) AND uses `duckdb.connect(...)` — the monkeypatch replaces the
`duckdb` reference visible inside that import scope.

### Peak RSS exceeds 512 MB / 1024 MB

Cause A: `_run_bridge_join` is materializing the candidate DataFrame back into Python
(e.g., calling `.df()` on `path_b_candidates` before the window function runs).
Fix: verify bridge_join.sql executes end-to-end in a single `con.execute(bridge_sql).df()`
call — all CTEs run in DuckDB, only the final result returns to Python.

Cause B: Arrow batch construction for 50k events is larger than expected.
Diagnosis: add `tracemalloc` snapshot before/after `_make_overlap_base_events` to
isolate input-data allocation from JOIN allocation.

Cause C: DuckDB temp_directory spill is not working (disk full, permissions).
Fix: set `DUCKDB_JOB_DIR` to a writable NVMe path and verify spill via DuckDB profiling:
```python
con.execute("PRAGMA enable_profiling")
```

### test_multi_resourceid_fan_out_scales_linearly exceeds 120 s

Cause: `duckdb.connect` is being called 100+ times (50 groups × 2 tables per group)
with cold DuckDB initialisation.  Each cold connect on a constrained CI runner can
take 50–200 ms.

Fix options:
1. Re-use a single DuckDB connection per group (connection-pool pattern) — DowntimeJob
   already does this in the real path via `_writer_lock`.
2. Use an in-memory DuckDB for the multi-resource test (no spill needed at 100k candidates).

### match_ambiguous dtype is object / None-only

Cause: bridge_join.sql `CASE WHEN ... THEN TRUE ELSE FALSE END` is returning a
string `'True'/'False'` or NULL because the `path_b_candidates` CTE is empty
(no overlapping candidates) and DuckDB infers the column type from an empty set.

Fix: confirm the synthetic data generator creates overlapping time windows (verify
`event_start < job COMPLETEDATE` and `event_end > job CREATEDATE`).  If the generator
is correct, add `TRY_CAST(match_ambiguous AS BOOLEAN)` in bridge_join.sql.

---

## Deferred: Soak Test

The soak test (24-hour looping DowntimeJob invocation) is deferred to the weekly
cadence and is NOT a pre-merge gate.

**Location:** `tests/integration/test_soak_workload.py` (extend when file exists)

**Proposed extension:**

```python
@pytest.mark.soak
def test_downtime_unified_job_24h_soak(tmp_path):
    """24-hour soak: DowntimeJob._run_bridge_join repeated 1000× (simulating
    ~2.4 min average request interval on a busy factory shift).

    Thresholds:
      - RSS growth < 2% per hour (< 48% total over 24h from warm baseline)
      - No MemoryError across all 1000 iterations
      - DUCKDB_JOB_DIR temp files: all cleaned after each iteration
        (base class 'finally' deletes job-temp DuckDB)
    """
    ...
```

**Soak dimensions not yet validated:**
- Temp file accumulation in `DUCKDB_JOB_DIR/downtime/` across many failed jobs
  (base class `finally` covers success; fault-injection needed for partial-failure)
- Connection pool (Oracle oracledb) under sustained DowntimeJob fan-out for 24h
- RSS growth rate under weekly scheduled runs (Linux page-cache reclaim behaviour)

File this as a follow-on task once `DOWNTIME_USE_UNIFIED_JOB=on` is promoted to
default (flag retirement milestone).
