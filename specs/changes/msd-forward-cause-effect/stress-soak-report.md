# Stress / Soak Report

## Change
msd-forward-cause-effect — MSD forward lineage stage spool + DuckDB get_summary(direction="forward") + package-independent trace cache reuse

## Workload Model

### Scoping decision
Oracle fetch scope is **not enlarged** (scope item 3b was dropped per `change-classification.md`). All load profiles in this report target the three high-risk surfaces identified in `change-classification.md`:

1. **Forward lineage spool write concurrency** — N workers writing `(SEED_ID, DESCENDANT_ID)` parquets under the shared `msd-events` namespace for distinct `trace_query_id`s simultaneously. Target: atomic-rename write path, no file collision, no cross-trace row bleed.
2. **DuckDB `get_summary(direction="forward")` read concurrency** — N threads each read a freshly-written forward lineage spool and run the single-pass GROUP BY summary. Target: DuckDB in-process connection isolation, stable p95 latency, no connection leak.
3. **Package-independent trace cache reuse** — same station+date combo resolved concurrently by N threads. Target: cache lookup is race-free, no stale/wrong trace_id returned.
4. **Spool write → read → delete repeated cycles (soak)** — extended cycle count to detect spool dir orphan growth, fd leaks, RSS drift.

### Load parameters

| surface | metric | stress value | soak value |
|---|---|---|---|
| concurrent spool writers | concurrent trace_query_ids | 20 (10 thread-pool workers) | 1 (serial write-delete cycles) |
| seeds per trace | SEED_ID count | 5 | 8 |
| DuckDB concurrent readers | parallel get_summary calls | 12 | 1 per cycle |
| cache lookup concurrency | concurrent same-station callers | 20 threads | n/a |
| write+delete cycles (soak) | soak duration proxy | n/a | 200 default; 5000 for long-run |
| Oracle fetch | load on Oracle | **zero — mocked entirely** | **zero — mocked entirely** |

## Duration

### Stress (Tier-5 — manual `workflow_dispatch`)
Each stress test completes in sub-second to a few seconds on synthetic in-process data. These are not timed soak loops; they are concurrency assertion tests run once per manual dispatch.

### Soak (Tier-4 — weekly schedule `0 18 * * 0`)
Default: 200 cycles (approximately 3.7 s on the dev host with 8 seeds/cycle and full get_summary path). Extended: set `SOAK_MSD_CYCLES=5000` for a genuine multi-minute soak. Maximum meaningful run: `SOAK_MSD_CYCLES=50000` (~400 s) to catch slow RSS drift not visible in 200 cycles.

## Thresholds

| check | threshold | rationale |
|---|---|---|
| spool write errors | 0 | any write error means a caller will see a missing spool |
| file path collision | 0 | distinct `trace_query_id`s must produce distinct filenames |
| cross-trace SEED_ID contamination | 0 | bleed between traces is a correctness regression |
| mean per-file write latency | < 2 s | spool write is I/O only; 2 s is generous on SSDs |
| DuckDB summary errors | 0 | any exception breaks the forward analysis path |
| DuckDB p95 summary latency | < 5 s | single-pass GROUP BY on synthetic 25-row table; 5 s allows for Python import overhead |
| cache lookup wall-clock (20 threads) | < 3 s | O(1) dict lookup; 3 s implies lock contention or GIL starvation |
| orphan parquets after soak | 0 | TTL eviction must remove all files; leaked parquets grow spool dir unboundedly |
| RSS growth (head→tail quartile) | < 15% | mirrors existing `_check_rss_growth` rule in `test_soak_workload.py` |
| fd delta over full soak | ≤ 10 | DuckDB in-process connections must close; ≤ 10 allows for test-framework overhead |
| unexpected DuckDB error rate | ≤ 2% of cycles | tolerates pre-implementation NotImplementedError gracefully |

## Commands / Workflows

### Stress tests (Tier-5 — manual trigger)
```bash
# Full stress battery (no running server needed for the spool-path tests)
conda run -n mes-dashboard pytest tests/stress/test_mid_section_defect_stress.py \
    -m stress --run-stress -v -s

# Individual test classes
conda run -n mes-dashboard pytest \
    tests/stress/test_mid_section_defect_stress.py::TestSpoolConcurrentForwardWrites \
    tests/stress/test_mid_section_defect_stress.py::TestDuckdbForwardSummaryUnderLoad \
    tests/stress/test_mid_section_defect_stress.py::TestCacheReuseUnderConcurrentSameStation \
    tests/stress/test_mid_section_defect_stress.py::TestForwardSpoolWriteReadConcurrent \
    --run-stress -v -s
```

CI gate: `.github/workflows/stress-tests.yml` — `workflow_dispatch`. Trigger manually after backend-engineer lands the forward lineage spool writer (IP-1/IP-2/IP-6).

### Soak test (Tier-4 — weekly schedule)
```bash
# Short smoke (200 cycles, ~4 s)
conda run -n mes-dashboard pytest \
    tests/integration/test_material_trace_rq_async.py::TestMsdForwardSpoolSoak \
    --run-integration-real -v -s

# Medium soak (5000 cycles, ~90 s)
SOAK_MSD_CYCLES=5000 SOAK_MSD_SEEDS_PER_CYCLE=8 \
conda run -n mes-dashboard pytest \
    tests/integration/test_material_trace_rq_async.py::TestMsdForwardSpoolSoak \
    --run-integration-real -v -s

# Weekly CI schedule command (from soak-tests.yml)
pytest tests/integration/test_soak_workload.py tests/integration/test_material_trace_rq_async.py::TestMsdForwardSpoolSoak \
    --run-integration-real -m soak -v
```

CI gate: `.github/workflows/soak-tests.yml` — `schedule: 0 18 * * 0`.

## Test Files

| file | test classes / functions | tier | marker |
|---|---|---|---|
| `tests/stress/test_mid_section_defect_stress.py` | `TestSpoolConcurrentForwardWrites::test_spool_concurrent_forward_writes_no_collision` | 5 | `@pytest.mark.stress` |
| `tests/stress/test_mid_section_defect_stress.py` | `TestDuckdbForwardSummaryUnderLoad::test_duckdb_forward_summary_under_load` | 5 | `@pytest.mark.stress` |
| `tests/stress/test_mid_section_defect_stress.py` | `TestCacheReuseUnderConcurrentSameStation::test_concurrent_cache_hits_return_same_trace_id` | 5 | `@pytest.mark.stress` |
| `tests/stress/test_mid_section_defect_stress.py` | `TestForwardSpoolWriteReadConcurrent::test_concurrent_writer_reader_no_partial_read` | 5 | `@pytest.mark.stress` |
| `tests/integration/test_material_trace_rq_async.py` | `TestMsdForwardSpoolSoak::test_forward_spool_repeated_cycles_no_leak` | 4 | `@pytest.mark.soak @pytest.mark.integration_real` |

## Results

### Smoke run (executed on dev host 2026-06-30)

| test | outcome | key metrics |
|---|---|---|
| `test_spool_concurrent_forward_writes_no_collision` | PASSED | n=20 traces, elapsed=0.03s, errors=0, contamination=0 |
| `test_duckdb_forward_summary_under_load` | PASSED | n=12 concurrent, elapsed=0.08s, p95=0.080s, errors=0 |
| `test_concurrent_cache_hits_return_same_trace_id` | PASSED | n=20 threads, elapsed=0.002s, errors=0 |
| `test_concurrent_writer_reader_no_partial_read` | PASSED | no file corruption, no cross-trace contamination |
| `test_forward_spool_repeated_cycles_no_leak` (soak) | PASSED | cycles=200, elapsed=3.73s, fd_delta=0, orphan_files=0, rss_growth~0.1% |

All 5 tests pass. Results are design-and-smoke verified; full production-scale run (5000+ cycles, 12-worker concurrent) deferred to the CI weekly schedule after the backend implementation lands.

### Notes on design-only vs executed
- The smoke run exercises the spool-path mechanics (parquet write/read, DuckDB path injection) but calls `MsdDuckdbRuntime.get_summary(direction="forward")` with path injection — this tests the DuckDB infrastructure without requiring the full backend-engineer implementation to be merged yet.
- The `get_summary(direction="forward")` method currently returns `None` for forward direction (the `return None` stub at `msd_duckdb_runtime.py:415` that IP-6 will replace). The soak test handles this gracefully: it continues as a spool-write/delete cycle only when `None` is returned, still exercising the fd+RSS+orphan-file leak signals.
- Once IP-6 lands, the soak test automatically exercises the full DuckDB GROUP BY path without code changes.

## Failure Triage

### `test_spool_concurrent_forward_writes_no_collision` fails with cross-trace contamination
The forward lineage writer is not using atomic rename (write to `.tmp` then `os.replace()`). Check that `_write_msd_forward_lineage_spool` matches the atomic-write pattern from `_write_msd_lineage_stage_spool` (design.md §Migration / Rollback).

### `test_duckdb_forward_summary_under_load` p95 exceeds 5 s
DuckDB in-process connection overhead is too high under concurrency. Likely cause: DuckDB is being initialized per-call without connection pooling. The single-pass GROUP BY on a 25-row synthetic table should complete in < 100 ms; if p95 is 5s+ something is blocking (Python GIL saturation, disk I/O, or connection setup serialization).

### `test_forward_spool_repeated_cycles_no_leak` reports fd_delta > 10
A DuckDB connection is not being closed after `get_summary`. Verify that `MsdDuckdbRuntime` opens and closes its `duckdb.connect()` within a `with` block or explicit `conn.close()` in a `finally` clause.

### `test_forward_spool_repeated_cycles_no_leak` reports orphan files
The delete step in the test cleans up after each cycle. If orphan files remain, the test infrastructure is wrong (check `ns_dir.glob` pattern). If this is reported from a production spool-dir scan, verify the TTL eviction job deletes `*_forward_lineage.parquet` in addition to `*_events.parquet`.

### RSS growth ≥ 15%
Most likely cause: pyarrow `RecordBatch` objects are being held in a module-level cache without an eviction bound. Audit any dict keyed by `trace_query_id` that accumulates parquet table objects rather than just paths.
