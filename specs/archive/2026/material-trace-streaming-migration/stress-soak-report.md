# Stress / Soak Report

## Workload Model

### S-1 — RQ-to-Oracle Concurrency Cap (weekly stress gate)

| dimension | value |
|---|---|
| user concurrency | 5 simulated workers (> cap of 3) |
| semaphore cap | `HEAVY_QUERY_MAX_CONCURRENT=3` |
| mock Oracle latency | 50ms per worker (enough to produce overlap) |
| retry window | 2s busy-wait per worker before marking timeout |
| Oracle / Redis required | no — in-process `threading.Semaphore` shim |

**What it verifies:** With 5 concurrent unified-job workers all contending for 3 slots, peak
simultaneous holders ≤ 3 at all times, and all 5 workers eventually complete (no starvation).
This proves the `acquire_heavy_query_slot` / `release_heavy_query_slot` contract holds under
overload without Redis.  Full Redis integration is covered by the Tier-3 nightly gate.

### S-2 — AC-5 Peak-Heap Non-Linearity Scaffold (weekly stress+soak gate)

| dimension | value |
|---|---|
| chunk count | 1, 3, 5 ID-list batches |
| rows per batch | 100 rows × 6 columns (Arrow RecordBatch) |
| materialization | real parquet write per chunk (mirrors `_fan_out_append`) |
| memory instrument | `tracemalloc` (peak heap KB, two runs, second measurement taken) |
| Oracle / Redis required | no — synthetic Arrow batches, no DB access |

**What it verifies:** Peak heap growth is sublinear when chunk count scales from 1 to 5 (a 5×
increase).  Peak(N=5) / Peak(N=1) < 1.5 threshold ensures that on-disk parquet spill prevents
in-memory accumulation from growing proportionally with the number of ID batches.

### AC-8 — Material-Trace 1000-ID Boundary (weekly stress gate)

| dimension | value |
|---|---|
| ID-list sizes tested | 999, 1000, 1001, 2000, 2001, 5000 + empty |
| batch size | 1000 (matches `material_trace_service._IN_BATCH_SIZE`) |
| Oracle / server required | no — pure arithmetic assertion |

**What it verifies:** `decompose_by_ids` at the 1000-ID boundary produces the correct batch count,
no batch exceeds 1000 IDs, and no ID is lost or duplicated across batches.

## Duration

- S-1: ~0.5s (5 workers × 50ms + thread overhead); not a long-duration soak
- S-2: ~0.3s per measurement × 2 runs × 3 chunk sizes per test; ~2s total; scaffold only
- AC-8: < 0.1s; pure arithmetic

Full 10-minute soak with flag=on (100/1000/5000 ID-list sizes against production Oracle) is
deferred to the weekly gate after flag promotion.  See "Deferred Evidence" below.

## Metrics

| metric | S-1 result | S-2 result |
|---|---|---|
| peak concurrent jobs | ≤ 3 (cap enforced) | n/a |
| workers completed | 5/5 (no starvation) | n/a |
| heap peak N=1 | n/a | measured (≈ 50–200 KB typical) |
| heap peak N=3 | n/a | measured |
| heap peak N=5 | n/a | measured |
| ratio peak(5)/peak(1) | n/a | < 1.5 (PASS) |
| AC-8 batches at n=999 | n/a | 1 batch, max_size=999 |
| AC-8 batches at n=1000 | n/a | 1 batch, max_size=1000 |
| AC-8 batches at n=1001 | n/a | 2 batches, max_size=1000 |
| AC-8 batches at n=5000 | n/a | 5 batches, max_size=1000 |

## Thresholds

| threshold | value | source |
|---|---|---|
| peak simultaneous jobs | ≤ `HEAVY_QUERY_MAX_CONCURRENT` (default 3) | global_concurrency.py L30; business-rules.md D3 |
| worker starvation | 0 timeouts in 5 workers (2s retry window) | S-1 design |
| peak heap ratio | peak(N=5) / peak(N=1) < 1.5 | AC-5; conservative headroom |
| batch size | ≤ 1000 IDs/batch | implementation-plan.md IP-3; material_trace_service.py L47 |
| error budget (pre-merge, flag=off) | no behavioral regression | AC-1 |
| soak RSS leak (production) | < 2% per 24h | deferred to flag=on weekly soak |

## Commands / Workflows

Weekly stress gate command (ci-gates.md stress-load tier 4):

```bash
# Stress — weekly gate (flag=on environment only)
conda run -n mes-dashboard pytest \
  tests/stress/test_material_trace_stress.py \
  tests/stress/test_chunk_boundary.py \
  -v --tb=short --run-stress -m "stress or soak"
```

Pre-merge verification (non-stress/soak only, 8 baseline tests):

```bash
conda run -n mes-dashboard pytest \
  tests/stress/test_material_trace_stress.py \
  tests/stress/test_chunk_boundary.py \
  -v --tb=short -m "not stress and not soak"
```

Full 10-minute AC-5 soak after flag promotion:

```bash
# Run in environment with MATERIAL_TRACE_USE_UNIFIED_JOB=on
conda run -n mes-dashboard pytest \
  tests/integration/test_soak_workload.py::test_material_trace_peak_heap_nonlinear \
  -v --tb=short --run-integration-real
```

## Results

Pre-merge baseline (8 non-stress tests): 8 passed in 0.24s.

Weekly stress scaffold (10 new tests with `--run-stress`): 10 passed in 0.35s.

All AC-8 boundary probes registered in session chunk-boundary summary:
- `n=999` → 1 batch, max_size=999 OK
- `n=1000` → 1 batch, max_size=1000 OK
- `n=1001` → 2 batches, max_size=1000 OK
- `n=2000` → 2 batches, max_size=1000 OK
- `n=2001` → 3 batches, max_size=1000 OK
- `n=5000` → 5 batches, max_size=1000 OK
- empty list → 1 empty batch OK

## Deferred Evidence (flag promotion gate)

AC-5 full soak evidence requires `MATERIAL_TRACE_USE_UNIFIED_JOB=on` to be set in a
production-equivalent environment.  The deferred soak workload (test-plan.md):

- Target: `tests/integration/test_soak_workload.py::test_material_trace_peak_heap_nonlinear`
- Duration: 10-minute continuous run
- ID-list sizes: 100 / 1000 / 5000 IDs (materializing real Oracle → Arrow → DuckDB parquet)
- Expected: peak heap growth < 1.5× when ID-list grows 50× (100 → 5000 IDs)
- Pass criteria for flag promotion:
  1. S-1 concurrency cap verified (peak ≤ 3, no starvation) — scaffolded and passing
  2. S-2 heap ratio < 1.5 across simulated chunks — scaffolded and passing
  3. Full 10-minute soak peak heap < 1.5× ratio at 100/1000/5000 sizes — NOT yet run
  4. Tier-3 parity (AC-4 spool schema equivalence) — NOT yet run
  5. soak/stress reports retained for 90d per ci-gates.md artifact retention policy

## Failure Triage

**S-1 peak > 3:** Semaphore not acquired correctly or release missing in finally block.
Check `acquire_heavy_query_slot` call site in `MaterialTraceJob` and ensure `release_heavy_query_slot`
is in a `finally` clause.  Also confirm `HEAVY_QUERY_MAX_CONCURRENT` env var is not overridden.

**S-2 ratio ≥ 1.5:** DuckDB on-disk spill is not active.  Causes: (a) batch data held in a
module-level list accumulating across chunks — fix by deleting batch reference after `pq.write_table`;
(b) `_fan_out_append` not being called (legacy `pd.concat` path still active on flag=on) — check
flag branch in `api_material_trace_query`; (c) `tracemalloc` measuring Python GC overhead — re-run
with gc.collect() before each measurement.

**AC-8 batch count wrong:** `decompose_by_ids` loop uses `len(ids)` instead of `max(len(ids), 1)` —
empty-list case would produce 0 batches; service L216 uses the `max(len, 1)` guard.  If batch count
is off-by-one at the 1000 boundary, check slice indexing (`ids[i:i+1000]` vs `ids[i:i+999]`).

**Full soak OOM:** If production soak shows heap growing faster than 1.5×, enable explicit DuckDB
`PRAGMA memory_limit` in `MaterialTraceJob.post_aggregate` and verify `requires_cross_chunk_reduction=False`
so `_fan_out_append` is used (not `_fan_out_reduction` which holds a shared DuckDB in memory).
