# Archive: unified-query-core-infra

> **Cold Data Warning**: This archive is historical evidence. Current requirements
> live in `contracts/` and active project guidance.

---

## Change Summary

Added three new foundation modules (`BaseChunkedDuckDBJob`, `QueryCostPolicy`,
`OracleArrowReader`) to `src/mes_dashboard/core/` as the P0 step of the
query-dataflow unification migration plan. These modules establish the shared
infrastructure that P1–P5 domain migrations will build on: a chunked Oracle →
Arrow → DuckDB/parquet streaming pipeline, a 4-layer SYNC/ASYNC routing
classifier, and a fork-safe per-worker Oracle Arrow connection pool. No existing
routes, services, workers, or frontend were modified; all three modules ship
with zero callers until P1 wires a domain.

---

## Final Behavior

- **BaseChunkedDuckDBJob** (abstract): template-method `run()` orchestrates
  `pre_query → build_chunk_sql → chunk_to_duckdb → post_aggregate` with
  ChunkStrategy enum (TIME/ID_LIST/ROW_COUNT/SINGLE). Two fan-out paths:
  multi-parquet append (`requires_cross_chunk_reduction=False`) and
  single-writer DuckDB with `_writer_lock` (`=True`). Progress bracket
  5→15→90→100. Job-temp DuckDB created/deleted in `finally`.
- **QueryCostPolicy**: `classify_query_cost()` short-circuits L0 (spool hit →
  SYNC) → L1 (always-async domain → ASYNC) → L2 (date span ≥ threshold) → L3
  (COUNT(*) row count). `DeprecationWarning` emitted at call-time for any of
  the 4 legacy `*_ASYNC_DAY_THRESHOLD` env vars found in `os.environ`.
- **OracleArrowReader**: `_pool = None` at class level (never created at import,
  ADR-0004 fork-safety). `chunk_iter()` yields `pa.RecordBatch`; one conn per
  call; `finally: conn.close()`. CHAR columns stripped.
- **DUCKDB_JOB_DIR** env var: `tmp/duckdb_jobs` default (sibling of
  `QUERY_SPOOL_DIR`, Docker-portable).

---

## Final Contracts Updated

| Contract | Version | Change |
|---|---|---|
| `contracts/env/env-contract.md` | 1.0.13 → 1.0.14 | `DUCKDB_JOB_DIR` added; 4 `*_ASYNC_DAY_THRESHOLD` vars deprecated (removal deferred P5) |
| `contracts/env/.env.example.template` | — | `DUCKDB_JOB_DIR=tmp/duckdb_jobs` added |
| `contracts/env/env.schema.json` | — | `DUCKDB_JOB_DIR` property added |
| `contracts/data/data-shape-contract.md` | 1.18.0 → 1.19.0 | Oracle→Arrow→DuckDB/parquet streaming boundary section (9 invariants) |
| `contracts/CHANGELOG.md` | — | `[env 1.0.14]` + `[data 1.19.0]` entries |

---

## Final Tests Added

| File | AC | Key coverage |
|---|---|---|
| `tests/test_base_chunked_duckdb_job.py` | AC-1, AC-2, AC-5 | 4 strategies, 2 reduction paths, hook order, progress brackets, temp lifecycle |
| `tests/test_query_cost_policy.py` | AC-4, AC-7 | All 4 layers, short-circuit order, DeprecationWarning ×4, no-pandas AST check |
| `tests/test_oracle_arrow_reader.py` | AC-3, AC-8 | chunk_iter, conn.close finally, pool-not-at-import, empty/null/CHAR-strip |
| `tests/contract/test_env_duckdb_job_dir.py` | AC-6 | DUCKDB_JOB_DIR name + default in all 3 env contract files |
| `tests/integration/test_oracle_arrow_pool_lifecycle.py` | AC-3/AC-5 | `pytestmark=integration_real`; pool exhaustion+recovery, writer_lock concurrent, job-temp lifecycle |

Total: 62 targeted tests; 5-phase ladder passed (collect/targeted/changed-area/contract/full).

---

## Final CI/CD Gates

Required (pre-merge): `unit-mock-integration`, `contract-validate`, `cdd-kit-gate`, `lint` — all green on push.
Nightly (post-merge, must pass within 24 h): `nightly-oracle-pool` (tests/integration/test_oracle_arrow_pool_lifecycle.py).
Informational: `type-check` (mypy, 20-day promotion criteria).
No workflow files modified; existing `backend-tests.yml` and `contract-driven-gates.yml` coverage sufficient.

---

## Production Reality Findings

- `REJECT_ASYNC_DAY_THRESHOLD` existed in source (`reject_query_job_service.py`) but
  had never been documented in `env-contract.md`. Added and deprecated simultaneously.
- Actual `*_ASYNC_DAY_THRESHOLD` count is 4 (not 7 as estimated in the initial design
  doc). Design.md was updated; no vars were invented to match the estimate.
- 171 `tests/contract/samples/*.json` showed runtime-volatile drift (timestamps,
  memory readings, live Oracle error snapshots) unrelated to the 3 new modules.
  Committed separately as `chore(samples): refresh contract response samples`.
- Tier-floor conflict: cdd-kit flagged concurrency surface (writer_lock,
  ThreadPoolExecutor, Oracle pool) as requiring Tier 0. Resolved with
  `tier-floor-override` in `tasks.yml` because zero callers exist until P1;
  stress deferred to first domain migration per `design.md` Open Risks.

---

## Lessons Promoted to Standards

| Lesson | Classification | Target | Evidence |
|---|---|---|---|
| L4: `tier-floor-override` for zero-caller concurrency modules | promote-to-guidance | `CLAUDE.md` CDD Kit operations + `docs/cdd-kit-patterns.md` §tier-floor-override | qa-reviewer.yml B1 / tasks.yml:4 / agent-log/audit.yml |
| L5: Git staging scope — stage only completed change's dir | promote-to-guidance | `CLAUDE.md` CDD Kit operations + `docs/cdd-kit-patterns.md` §Git Staging Scope | pre-commit failure on `downtime-duckdb-join-migration` unfilled scaffold |
| L1: OracleArrowReader fork-safety | do-not-promote | — | already covered by ADR-0004 + data-shape-contract.md §streaming boundary |
| L2: `*_ASYNC_DAY_THRESHOLD` deprecation | do-not-promote | — | already in env-contract.md v1.0.14 + CHANGELOG |
| L3: DUCKDB_JOB_DIR portability | do-not-promote | — | already in env-contract.md + existing MEMORY portability rule |

---

## Follow-up Work

- **P1 `eap-alarm-unified-job-poc`**: first domain migration; will wire a real caller
  to BaseChunkedDuckDBJob and trigger concurrency stress tests deferred from P0.
- **Nightly gate**: `nightly-oracle-pool` must pass within 24 h of merge.
- **P5 cleanup**: remove the 4 deprecated `*_ASYNC_DAY_THRESHOLD` env vars and the
  `_DEPRECATED_THRESHOLD_VARS` runtime warning block in `query_cost_policy.py`.
