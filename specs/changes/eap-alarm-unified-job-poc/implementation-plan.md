---
change-id: eap-alarm-unified-job-poc
schema-version: 0.1.0
last-changed: 2026-06-19
---

# Implementation Plan: eap-alarm-unified-job-poc

## Objective

Migrate `run_eap_alarm_query_job` onto the P0 `BaseChunkedDuckDBJob` template
method as the first-in-class POC. Deliver: a new `EapAlarmJob` subclass with
parallel time-chunked Oracle fetch; a completed base-class per-chunk parquet
sink (R1); a unified `enqueue_query_job` entry-point with the always-async 503
decision tree; `JobTypeConfig.always_async`; and a route-level
`EAP_ALARM_USE_UNIFIED_JOB` flag (default off) selecting new-vs-legacy. New path
must be byte-for-row equivalent to legacy (schema + rowcount + business-key
row-set), and flag-OFF must be zero-regression. Spool key/path/schema and all
view endpoints are unchanged (non-goals).

## Execution Scope

### In Scope
- `BaseChunkedDuckDBJob._fan_out_append` per-chunk parquet sink + `_make_chunk_parquet_dir` helper (R1, base edit).
- `EapAlarmJob(BaseChunkedDuckDBJob)`: `pre_query` time-chunk decomposition, `build_chunk_sql`, `post_aggregate`, `progress_report` override; legacy `run_eap_alarm_query_job` kept intact.
- `JobTypeConfig.always_async` field; eap-alarm registered `always_async=True`.
- `enqueue_query_job(...)` unified entry-point with the D3 503 decision tree (per-call `sync_fallback_allowed`).
- Route flag gating in `api_eap_alarm_spool` (default off → legacy; on → unified).
- Contracts: env (`EAP_ALARM_USE_UNIFIED_JOB`), business-rules (unified routing + always-async 503), error-format (503 status), CHANGELOG + env.schema.json + .env.example.template.
- Tests: unit / contract / integration / data-boundary / resilience / e2e / stress / soak per change-classification §Required Tests.

### Out of Scope
- Frontend eap_alarm pages (view layer already in-memory DuckDB; no change).
- Migrating any other domain (production / reject / resource / material_trace / downtime).
- Changing spool parquet schema, spool key, `make_eap_alarm_spool_key`, `get_eap_alarm_spool_path`, or `_SCHEMA_VERSION` (ADR-0008 — no bump).
- `eap_alarm_service.py` / `eap_alarm_cache.py` logic (views + spool key unchanged).
- Removing legacy `run_eap_alarm_query_job` (deferred to P4/P5 cleanup; AC-8 coexistence gate).
- No opportunistic refactor of `enqueue_job` / `enqueue_job_dynamic` internals beyond adding the new entry-point.

## R1 Decision (`_fan_out_append` gap)

**Chosen: Option A — extend the base class minimally.**

The P0 default `_fan_out_append` (base lines 278-302) fetches each chunk then
discards every batch (`list(self._fetch_chunk(cp))` with no sink); `post_aggregate`
receives `None` and has nothing to read. Option A makes `_fan_out_append` write each
fetched `RecordBatch` to a per-chunk parquet file under a job-scoped dir, exposed via
a `_make_chunk_parquet_dir(job_id)` helper, so the `requires_cross_chunk_reduction=False`
fan-out becomes a reusable sink for every P2+ migration (production_history etc.).
Rationale: design.md §5 R1 explicitly recommends extending the base so P2+ migrations
do not each re-invent the per-chunk parquet sink, and this POC is the acceptance
template (D6) for all later domains — a subclass-only override (Option B) would force
each domain to reimplement the sink and defeat the template purpose. The base edit is
owned by backend-engineer (not spec-architect). Because this changes base behavior,
`tests/test_base_chunked_duckdb_job.py` MUST be updated in the same step (IP-1).

## Execution Order

Strict ordering (each gate must pass before the next starts):

1. **IP-1** (backend-engineer) — Fix base `_fan_out_append` + parquet sink. MUST be first; nothing else has a working append path.
2. **IP-2** (contract-reviewer) — Land env + business-rules + error-format contracts. MUST precede IP-4 (unified entry-point implements the contracted 503 routing) and IP-6 (route reads the contracted flag default).
3. **IP-3** (backend-engineer) — Add `JobTypeConfig.always_async`; register eap-alarm `always_async=True`.
4. **IP-4** (backend-engineer) — Implement `enqueue_query_job` 503 decision tree (depends on IP-2 contract + IP-3 field).
5. **IP-5** (backend-engineer) — Implement `EapAlarmJob` (depends on IP-1 sink).
6. **IP-6** (backend-engineer) — Flag-gated route dispatch (depends on IP-4 + IP-5).
7. **IP-7** (test-strategist + backend-engineer) — Tests written alongside IP-1/IP-4/IP-5/IP-6 (not after); seam unit fixture must exist before IP-5 is declared done.
8. **IP-8** (stress-soak-engineer) — Stress/soak surfaces + `stress-soak-report.md` (after IP-5/IP-6 land).
9. **IP-9** (ci-cd-gatekeeper) — Wire/verify CI gates + author `ci-gates.md`.

Tests-first discipline: for IP-1 write the base seam/sink test before/with the edit;
for IP-4 write the 503 dispatch test with the implementation; for IP-5 the mock-seam
parity unit test (D6) gates "done"; for IP-6 the flag-OFF parity test.

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | core base class (R1) | Implement per-chunk parquet sink in `_fan_out_append` + `_make_chunk_parquet_dir`; update base test | backend-engineer |
| IP-2 | contracts | Add env flag, business-rule routing/503, error-format 503, CHANGELOG/schema/.env bumps | contract-reviewer |
| IP-3 | job registry | Add `JobTypeConfig.always_async`; register eap-alarm `always_async=True` | backend-engineer |
| IP-4 | async enqueue | Add `enqueue_query_job` with D3 503 decision tree | backend-engineer |
| IP-5 | worker | Add `EapAlarmJob(BaseChunkedDuckDBJob)`; keep legacy worker | backend-engineer |
| IP-6 | route | Flag-gated dispatch in `api_eap_alarm_spool` | backend-engineer |
| IP-7 | tests | Unit/contract/integration/data-boundary/resilience/e2e per AC map | test-strategist + backend-engineer |
| IP-8 | stress/soak | Concurrency + soak surfaces + `stress-soak-report.md` | stress-soak-engineer |
| IP-9 | CI | Verify backend/stress/soak gates wire eap_alarm cases; author `ci-gates.md` | ci-cd-gatekeeper |

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| design.md | D1 (template contract), D2 (time-chunk), D3 (503 tree), D4 (flag), D5 (conn lifecycle), D6 (parity), §5 R1 | implementation constraints |
| design.md | ADR ref `docs/adr/0009-eap-alarm-cross-chunk-pairing-in-post-aggregate.md` | cross-chunk pairing rationale (post_aggregate reads ALL chunk parquets) |
| change-classification.md | AC-1..AC-8; §Required Tests; §Required Contracts | acceptance + test/contract scope |
| change-classification.md | Optional Artifacts: `stress-soak-report.md` = yes | IP-8 deliverable |
| change-request.md | §Non-goals; §Constraints | out-of-scope guardrails |
| docs/adr/0003-... | rowcount-chunking exclusion | why `chunk_strategy=TIME` + `requires_cross_chunk_reduction=False` is legal here |
| docs/adr/0008-... | coarse spool detail join; no `_SCHEMA_VERSION` bump | rollback / parity invariants |

## File-Level Plan

| path or glob | action | notes |
|---|---|---|
| `src/mes_dashboard/core/base_chunked_duckdb_job.py` | modify | IP-1: rewrite `_fan_out_append` (lines 278-302) to write each batch via `pyarrow.parquet.write_table` to `{chunk_dir}/chunk-{chunk_idx}-{batch_idx}.parquet`; add `_make_chunk_parquet_dir(job_id)` → `{DUCKDB_JOB_DIR}/{namespace}/{job_id}/`; pass chunk index into the per-chunk callable. Each chunk thread writes its OWN files → no `_writer_lock` needed on the append path. |
| `src/mes_dashboard/services/job_registry.py` | modify | IP-3: add `always_async: bool = False` to `JobTypeConfig` (after `should_enqueue`). Keep `sync_fallback_allowed` as a per-call arg of `enqueue_query_job`, NOT a registry field (design.md §5 deferred → per-call recommended). |
| `src/mes_dashboard/services/async_query_job_service.py` | modify | IP-4: add `enqueue_query_job(job_type, owner, params, *, sync_fallback_allowed=True, job_id=None)` returning `(job_id_or_None, error_or_None, http_status)` (or an equivalent result object test-strategist pins). Reuse `get_job_type_config`, `is_async_available`, `enqueue_job_dynamic`/`enqueue_job` internals. Do not alter existing functions' signatures. |
| `src/mes_dashboard/workers/eap_alarm_worker.py` | modify | IP-5: add `class EapAlarmJob(BaseChunkedDuckDBJob)`; reuse `_EAP_EVENT_SQL_TEMPLATE`, `_DETAIL_SQL_TEMPLATE`, `_PAIR_SQL`, `_build_equipment_filter`, `make_eap_alarm_spool_key`, `get_eap_alarm_spool_path`, `register_spool_file`. Keep `run_eap_alarm_query_job` + its `register_job_type(...)` block untouched; add `always_async=True` to that registration (IP-3 field). |
| `src/mes_dashboard/routes/eap_alarm_routes.py` | modify | IP-6: in `api_eap_alarm_spool` (lines 158-205) read `EAP_ALARM_USE_UNIFIED_JOB` via `resolve_bool_flag` (default `False`); OFF → existing `enqueue_job(... run_eap_alarm_query_job ...)` block unchanged; ON → `enqueue_query_job("eap-alarm", ...)` and map a 503 result to the existing `error_response(SERVICE_UNAVAILABLE, ... status_code=503, Retry-After)` shape. Keep spool-hit branch (lines 148-156) and 202 success shape identical for both paths. |
| `contracts/env/env-contract.md` | modify | IP-2: register `EAP_ALARM_USE_UNIFIED_JOB`, default `off`/`false`. |
| `contracts/env/env.schema.json` | modify | IP-2: add property for the flag. |
| `contracts/env/.env.example.template` | modify | IP-2: add flag line with default. |
| `.env.example` | modify | IP-2: add flag line with default. |
| `contracts/business/business-rules.md` | modify | IP-2: document unified enqueue routing + `always_async`⇒503-on-forced-sync (no silent downgrade). |
| `contracts/api/error-format.md` | modify | IP-2: document 503 `SERVICE_UNAVAILABLE` + `Retry-After` for always-async forced-sync. |
| `contracts/CHANGELOG.md` | modify | IP-2: bump env schema-version + business schema-version (version entries go ONLY here). |
| `tests/test_base_chunked_duckdb_job.py` | modify | IP-1/IP-7: cover append parquet-sink path (AC-2 seam). |
| `tests/test_eap_alarm_service.py` | modify | IP-7: unit — chunk decomposition (AC-2), progress bracket, mock-seam parity (AC-1/D6). |
| `tests/test_async_query_job_service.py` | modify | IP-7: unit — `enqueue_query_job` 503 decision tree (AC-4/AC-5). |
| `tests/integration/test_eap_alarm_rq_async.py` | modify | IP-7: flag-ON vs flag-OFF parquet diff parity (AC-1/AC-8). |
| `tests/integration/test_eap_alarm_data_boundary.py` | modify | IP-7: spool schema + rowcount parity (data-boundary). |
| `tests/integration/test_eap_alarm_resilience.py` | modify | IP-7: chunk fault injection, no partial-result corruption (AC-6). |
| `tests/integration/test_oracle_arrow_pool_lifecycle.py` | modify | IP-7: connection returned via `finally` no leak (AC-6). |
| `tests/integration/test_rowcount_flag_parity.py` | modify | IP-7: rowcount parity across flag (AC-1/AC-8). |
| `tests/e2e/test_eap_alarm_e2e.py` | modify | IP-7: flag-ON e2e identical result set + coarse progress tolerated (AC-3/R3). |
| `tests/integration/test_soak_workload.py` | modify | IP-8: sustained load, no connection leak, bounded memory peak. |
| `tests/stress/test_async_job_stress.py` | modify | IP-8: ThreadPoolExecutor concurrency, pool non-exhaustion (AC-3/AC-6). |
| `tests/stress/test_chunk_boundary.py` | modify | IP-8: no-duplication / no-loss across daily seam under parallel load (AC-2/R2). |
| `tests/contract/` | create/modify | IP-2/IP-7: env default-value pin (AC-7) + business-rule 503 assertion. |
| `specs/changes/eap-alarm-unified-job-poc/stress-soak-report.md` | create | IP-8 deliverable. |
| `specs/changes/eap-alarm-unified-job-poc/ci-gates.md` | modify (fill scaffold) | IP-9 deliverable. |

## Implementation Steps (detail)

### IP-1 — Fix base `_fan_out_append` (R1) — backend-engineer
- File: `src/mes_dashboard/core/base_chunked_duckdb_job.py`.
- Add `_make_chunk_parquet_dir(self, job_id)` → `Path(os.environ.get("DUCKDB_JOB_DIR", DUCKDB_JOB_DIR)) / self.namespace / job_id`, `mkdir(parents=True, exist_ok=True)`, return path. (Mirror `_make_job_duckdb_path` style, lines 233-238.)
- Rewrite `_fan_out_append`: per-chunk callable receives the chunk index; for each `RecordBatch` in `_fetch_chunk(cp)`, write to `{chunk_dir}/chunk-{chunk_idx}-{batch_idx}.parquet` via `pyarrow.parquet.write_table(pa.Table.from_batches([batch]), path)`. Preserve serial-vs-parallel branch and the `as_completed` re-raise (lines 291-302). No `_writer_lock` (each thread owns distinct files).
- Empty-chunk / zero-batch case must leave the dir present and writable so `post_aggregate` can glob to an empty set safely.
- Acceptance: AC-2 (base seam fixture). Update `tests/test_base_chunked_duckdb_job.py` same step.

### IP-2 — Contracts — contract-reviewer
- See File-Level Plan rows. Default MUST be `off`/`false`; env-contract test pins the default (AC-7). Business-rule MUST state always-async + `sync_fallback_allowed=False` ⇒ 503, never silent downgrade (AC-4). error-format documents the 503 status + `Retry-After`. Version entries only in `contracts/CHANGELOG.md`. Acceptance: AC-4, AC-7.

### IP-3 — `JobTypeConfig.always_async` — backend-engineer
- Add field `always_async: bool = False` to dataclass (`job_registry.py` after line 45). Add `always_async=True` to the eap-alarm `register_job_type(...)` block in `eap_alarm_worker.py` (lines 283-289). Acceptance: AC-2 (flag presence), AC-5.

### IP-4 — Unified `enqueue_query_job` — backend-engineer
- File: `async_query_job_service.py`. New function implementing D3 decision tree:
  1. spool hit → caller already handles (route checks spool first); entry-point itself assumes miss.
  2. `config.always_async=True` AND `is_async_available()` → enqueue (reuse `enqueue_job_dynamic`), return 202 outcome.
  3. `always_async=True` AND `sync_fallback_allowed=False` AND NOT available → 503 outcome (no enqueue, no sync).
  4. `always_async=False` AND not available AND `sync_fallback_allowed=True` → sync-fallback outcome (not used by eap_alarm).
- Return contract: pin a 3-tuple `(job_id|None, error|None, http_status)` OR a small result object — test-strategist locks the exact shape in `test_async_query_job_service.py` before route consumes it (IP-6). Acceptance: AC-4, AC-5.

### IP-5 — `EapAlarmJob` — backend-engineer
- File: `eap_alarm_worker.py`. Class attrs: `namespace="eap_alarm"`, `chunk_strategy=ChunkStrategy.TIME`, `requires_cross_chunk_reduction=False`, `max_parallel=3`.
- `pre_query`: parse `(date_from, date_to, machines)`; resolve spool key via `make_eap_alarm_spool_key` (unchanged); split `[date_from, date_to]` into daily windows; emit per-window chunk_params carrying `kind` ∈ {"events","detail"} + window binds (two SQL kinds per window per D2).
- `build_chunk_sql(chunk_params)`: return `(events_sql|detail_sql, binds)` for the window using existing templates + `_build_equipment_filter`.
- `post_aggregate(job_duckdb_path=None)`: `job_duckdb_path` is `None` (append path); glob `chunk-*.parquet` from `_make_chunk_parquet_dir(self.job_id)`; in DuckDB read events vs detail parquet sets via `read_parquet(glob)`, run the EAV pivot + `_PAIR_SQL` pairing **over the full chunk set** (cross-seam SET/CLEAR — ADR-0009), `COPY TO` the existing `get_eap_alarm_spool_path(spool_key)`; `register_spool_file("eap_alarm", ...)` with rowcount. The legacy in-Python pandas EAV pivot moves into DuckDB SQL here (D2 fidelity improvement — parity test must pin full row-set, not count-only).
- `progress_report(pct)`: call `update_job_progress(_JOB_PREFIX, self.job_id, ...)`; base brackets 5→15→90→100 (coarser than legacy 6-stage; accepted per R3).
- Connection lifecycle: each chunk acquires/releases its own Oracle conn inside `OracleArrowReader.chunk_iter` `finally: conn.close()` (base/reader, lines 139-140) — do NOT re-open conns in `EapAlarmJob` (AC-6).
- Keep legacy `run_eap_alarm_query_job` byte-for-byte. Acceptance: AC-1, AC-2, AC-3, AC-6.

### IP-6 — Flag-gated route — backend-engineer
- File: `eap_alarm_routes.py` `api_eap_alarm_spool`. Read flag (default off); OFF path = current lines 159-205 unchanged; ON path calls `enqueue_query_job("eap-alarm", owner=get_owner_token(), params={date_from,date_to,machines}, sync_fallback_allowed=False)` and maps 503 outcome to the existing `error_response(SERVICE_UNAVAILABLE, ..., status_code=503, headers={"Retry-After": ...})` (lines 189-195) and 202 outcome to the existing success shape (lines 197-205). Spool-hit branch unchanged. Acceptance: AC-4, AC-5, AC-8.

### IP-7 — Tests — test-strategist + backend-engineer
- See File-Level Plan + AC map below. Mock-seam unit fixture (SET in chunk-1, CLEAR in chunk-2) gates IP-5 "done" (D6). Integration tier diffs the two parquets directly (flag ON vs OFF) on same seeded input.

### IP-8 — Stress / soak — stress-soak-engineer
- `tests/stress/test_chunk_boundary.py`, `tests/stress/test_async_job_stress.py`, `tests/integration/test_soak_workload.py`; produce `stress-soak-report.md` covering pool exhaustion/leak under fan-out, memory-peak non-linearity (AC-3), chunk no-dup/no-loss under concurrent load (AC-2). This invalidates P0's `tier-floor-override` deferral.

### IP-9 — CI gates — ci-cd-gatekeeper
- Verify `backend-tests.yml` discovers new tests; confirm stress/soak workflows include eap_alarm cases (weekly/manual, not pre-merge); fill `ci-gates.md` (must contain literal "workflow" / "promotion policy" / "rollback policy" headers).

## Contract Updates

- API: error-format only — 503 `SERVICE_UNAVAILABLE` + `Retry-After` for always-async forced-sync (`contracts/api/error-format.md`). No endpoint shape change; spool schema/rowcount held equivalent.
- CSS/UI: none.
- Env: `EAP_ALARM_USE_UNIFIED_JOB` default `off`/`false` in `env-contract.md`, `env.schema.json`, `.env.example.template`, `.env.example`; default pinned by env-contract test (AC-7).
- Data shape: none — spool parquet schema unchanged (non-goal); equivalence is a test AC, not a contract change. No `_SCHEMA_VERSION` bump (ADR-0008).
- Business logic: unified enqueue routing + `always_async`⇒503-on-forced-sync in `business-rules.md`.
- CI/CD: none new — reuse existing backend/stress/soak workflows (verified by IP-9).

## Test Execution Plan

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 (schema+rowcount+row-set parity) | tests/integration/test_eap_alarm_rq_async.py | flag ON vs OFF parquets identical on `(EQP_ID,ALARM_ID,ALARM_START)` set |
| AC-1 (mock-seam unit parity) | tests/test_eap_alarm_service.py | cross-seam SET/CLEAR paired in post_aggregate |
| AC-2 (chunk decomposition, no dup/loss) | tests/test_base_chunked_duckdb_job.py | append sink writes per-chunk parquet; glob recovers all rows once |
| AC-3 (parallel wall-time, bounded memory) | tests/stress/test_async_job_stress.py | concurrent chunk fan-out; memory not linear in result size |
| AC-4 (forced-sync 503) | tests/test_async_query_job_service.py | always_async + sync_fallback_allowed=False + unavailable → 503, no sync downgrade |
| AC-5 (unified entry-point) | tests/test_async_query_job_service.py | `enqueue_query_job` replaces Pattern A/B, exposes flags |
| AC-6 (connection no leak) | tests/integration/test_oracle_arrow_pool_lifecycle.py | every chunk conn returned via finally; resilience: 1 chunk fails, no corruption (tests/integration/test_eap_alarm_resilience.py) |
| AC-7 (env default pin) | tests/contract/ | `EAP_ALARM_USE_UNIFIED_JOB` default `off`/`false` pinned |
| AC-8 (flag-OFF zero regression) | tests/integration/test_rowcount_flag_parity.py | flag OFF identical to pre-change legacy path |

`cdd-kit test select` uses bare targets/files above; phases below. Stress/soak (IP-8) run in a separate CI workflow, not a pre-merge gate.

## Test Ladder (cdd-kit phases)

| phase | scope |
|---|---|
| collect | all new/modified test files discoverable by pytest |
| targeted | IP-7 unit: tests/test_eap_alarm_service.py, tests/test_base_chunked_duckdb_job.py, tests/test_async_query_job_service.py |
| changed-area | IP-7 integration: tests/integration/test_eap_alarm_rq_async.py, test_eap_alarm_data_boundary.py, test_eap_alarm_resilience.py, test_oracle_arrow_pool_lifecycle.py, test_rowcount_flag_parity.py |
| contract | IP-2 contract tests (env default pin AC-7, business-rule 503 assertion AC-4) via `cdd-kit validate` + tests/contract/ |
| quality | ruff on all modified/new files |
| full | full suite smoke (final/CI, not pre-merge) |
| stress/soak | tests/stress/* + tests/integration/test_soak_workload.py — separate CI workflow, not pre-merge gate |

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.
- `sync_fallback_allowed` is a per-call arg (not a registry field); `always_async` is the registry field. Do not invert this.
- Do not bump `_SCHEMA_VERSION` and do not change `make_eap_alarm_spool_key` / `get_eap_alarm_spool_path` (parity invariant).

## Known Risks

- R1 (high): P0 `_fan_out_append` discards batches — resolved by IP-1 (Option A base sink). Without IP-1 nothing downstream produces a parquet.
- R2 (medium): cross-chunk SET/CLEAR pairing — `post_aggregate` MUST read ALL chunk parquets together (ADR-0009); pinned by the D6 seam fixture (IP-7) and tests/stress/test_chunk_boundary.py (IP-8). Daily chunking must not change the legacy window-boundary drop behavior for CLEARs whose SET is outside the window.
- R3 (low): coarse 4-point progress vs legacy 6-stage — intentional; no frontend change; confirmed by E2E (IP-7).
- EAV pivot moves pandas→DuckDB (D2): a count-only parity test would miss a pairing regression → AC-1 requires full business-key row-set equality (IP-7).
- `enqueue_query_job` return shape: lock the exact tuple/object in IP-7 before IP-6 consumes it, to avoid route/service drift.
- `.cdd/code-map.yml` was generated 2026-06-18 (current); line ranges cited here verified against it.
