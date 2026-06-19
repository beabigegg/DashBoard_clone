# Archive: downtime-duckdb-join-migration

## Change Summary

Added `DowntimeJob(BaseChunkedDuckDBJob)` — a P5 migration that replaces the legacy `_bridge_jobid` Path B (`pd.merge`) with a streaming DuckDB-native path. The job fans out two Oracle Arrow streams (`base_events` + `job_data`) into separate raw tables (`base_raw`/`job_raw`) inside a per-job DuckDB file, then executes a cross-shift LAG/SUM window merge and a RANGE JOIN + LEAD-window time-overlap bridge in `post_aggregate`. The entire path is feature-flagged off by default (`DOWNTIME_USE_UNIFIED_JOB=off`), so there is zero behavioral change to production until the flag is explicitly promoted after stress-soak evidence is collected.

## Final Behavior

- `DOWNTIME_USE_UNIFIED_JOB=off` (default): legacy `execute_downtime_query_job` → `_bridge_jobid` pd.merge path unchanged.
- `DOWNTIME_USE_UNIFIED_JOB=on`: downtime-analysis route enqueues `DowntimeJob` via `enqueue_query_job('downtime-unified')`; always_async=True; sync_fallback_allowed=False; async unavailable → 503.
- Chunking: per-RESOURCEID group, `chunk_strategy=SINGLE`, `requires_cross_chunk_reduction=True`; ADR-0003 row-count chunking permanently excluded.
- Join: RANGE JOIN time-overlap bridge with LEAD-window 80% ambiguity flag; NOT ASOF JOIN (ADR-0010).
- Spool namespace `query_downtime_dataset` and parquet schema unchanged (18 columns, §3.21).

## Final Contracts Updated

| contract | bump | what changed |
|---|---|---|
| `contracts/env/env-contract.md` | 1.0.18 → 1.0.19 | DOWNTIME_USE_UNIFIED_JOB flag row added |
| `contracts/env/env.schema.json` | — | DOWNTIME_USE_UNIFIED_JOB with enum + default |
| `contracts/env/.env.example.template` | — | flag stub added |
| `.env.example` | — | flag stub added |
| `contracts/data/data-shape-contract.md` | 1.22.0 → 1.23.0 | §3.21 enriched-spool UNCHANGED assertion (18 cols, query_downtime_dataset only) |
| `contracts/business/business-rules.md` | 1.26.1 → 1.27.0 | DDA-01 (RANGE JOIN + window ADR-0010) + 3 Decision Table rows |
| `contracts/ci/ci-gate-contract.md` | 1.3.29 → 1.3.30 | gate compat note; downtime-unified reuses downtime-query queue |
| `contracts/CHANGELOG.md` | — | ci 1.3.30 entry added |

## Final Tests Added / Updated

| file | count | type |
|---|---|---|
| `tests/test_downtime_unified_job.py` | 27 | unit (6 classes): pre-query, chunk-to-db, post-aggregate, flag dispatch, spool-key, column-parity |
| `tests/contract/test_env_downtime_unified_flag.py` | 7 | contract: env-var pin, default, enum validation |
| `tests/integration/test_downtime_rq_async.py` | 8 | resilience: dispatch, parity, cancel, flag-off regression |
| `tests/stress/test_downtime_analysis_stress.py` | 3 | stress: OOM ceiling, on-disk spill |
| `tests/test_query_cost_policy.py` | modified | `downtime_worker` added to `_APPROVED_CALLERS` |
| `tests/test_job_registry.py` | modified | count 9 → 10; `downtime-unified` in expected set |

Evidence path: `specs/changes/downtime-duckdb-join-migration/agent-log/` + `test-evidence.yml` (final-status: passed).

## Final CI/CD Gates

Tier 0/1 merge gates (all passed locally):
- `ruff check .` (lint)
- `cdd-kit validate` (contract-validate)
- `cdd-kit validate --contracts` (response-shape-validate)
- `pytest` unit-mock-integration
- `cdd-kit gate downtime-duckdb-join-migration`

Non-blocking:
- Tier 3 nightly: `nightly-integration`, `oracle-fault-injection`
- Tier 4 weekly: `stress-load`, `soak` (soak extension point in `stress-soak-report.md`)
- `downtime-e2e` (informational, pending 60-run promotion threshold)

No new workflow YAML files; all tests auto-discovered by existing jobs.

## Production Reality Findings

- **fragment_count silent drop bug** (found by qa-reviewer): `_derive_job_columns` dropped `fragment_count` because it was not in the hardcoded column list. Fixed before merge; `test_derive_job_columns_preserves_fragment_count` added as AC-3/AC-8 guard. Evidence: `agent-log/stress-soak-engineer.yml` + final test count 20 → 27.
- **DuckDB patch target**: `mes_dashboard.workers.downtime_worker.duckdb.connect` (function-scope import), not `duckdb.connect`. Confirmed in stress test authoring.
- **Hot RESOURCEID (R2)**: Stress test confirmed 50k×5k (250M candidates) spills to disk; RSS bounded at 1GB. 6GB host can run 3 concurrent workers within headroom. No Python heap OOM. (`stress-soak-report.md`)
- **bridge_join.sql DISTINCT ON (JOBID)** requires DuckDB ≥0.8 (Path A dedup). Already met by current install; noted for future DuckDB downgrades.
- **Worker env-var parity**: contract-reviewer flagged that `mes-dashboard-downtime-worker.service` must export `DOWNTIME_USE_UNIFIED_JOB` with the same value as gunicorn. Not enforced by current tooling; risk if operator sets flag in one env only.
- **§3.21 scope precision**: Blanket "UNCHANGED" claim would have been false — `query_downtime_dataset_raw` (browser-DuckDB path, §3.13) has different columns. Contract correctly scopes the assertion to `query_downtime_dataset` only.

## Lessons Promoted to Standards

**Lesson A — `_derive_*` column-preservation guard (promote-to-contract)**
- Added to: `contracts/data/data-shape-contract.md §3.0` (new subsection); `contracts/CHANGELOG.md [data 1.23.1]`
- Rule: every `_derive_*` transform in a `BaseChunkedDuckDBJob` subclass must preserve all upstream spool columns it does not explicitly compute; enforce with a `test_derive_*_preserves_<column>` guard test in the same commit.
- Evidence: `_derive_job_columns` dropped `fragment_count` (§3.21); fixed by `tests/test_downtime_unified_job.py:test_derive_job_columns_preserves_fragment_count`.

**Lesson B — `*_USE_UNIFIED_JOB` worker env-var parity (promote-to-contract + guidance pointer)**
- Added to: `contracts/env/env-contract.md §Worker Feature-Flag Env-Var Parity` (new cross-cutting subsection); `contracts/CHANGELOG.md [env 1.0.20]`; `CLAUDE.md` Cache & spool patterns one-liner (pointer to contract).
- Rule: all `*_USE_UNIFIED_JOB` flags must be identical in gunicorn AND the RQ worker service environment; drift causes silent split-brain routing with no error log.
- Evidence: `agent-log/contract-reviewer.yml:15` finding; `archive.md` §Production Reality Findings; per-worker parity notes already in 4 prior flag descriptions (lines 91–94 of env-contract.md).

## Follow-up Work

- **AC-3 Oracle parity test**: `test_downtime_rq_async.py` parity test requires real Oracle + Redis; deferred to nightly gate (Tier 3). Triage SLA: 1 business day after first nightly failure.
- **Stress-soak promotion gate**: `stress-soak-report.md` exists but `DOWNTIME_USE_UNIFIED_JOB` must remain `off` until weekly soak shows stable RSS. Promotion checklist is in `stress-soak-report.md`.
- **downtime-e2e promotion**: `tests/e2e/test_downtime_analysis_e2e.py` starts informational; promote to required after 60 clean runs.
- **cross-shift merge SQL parity**: R3 decision used DuckDB LAG/SUM walk with pandas fallback. If SQL form diverges from pandas reference on real data, consider reverting merge to pandas.

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and active project guidance.
