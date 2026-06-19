---
change-id: downtime-duckdb-join-migration
schema-version: 0.1.0
last-changed: 2026-06-19
---

# Implementation Plan: downtime-duckdb-join-migration

## Objective

Deliver a flag-gated `DowntimeJob(BaseChunkedDuckDBJob)` that replaces the
`_bridge_jobid` Path B `pd.merge` (the system's #1 OOM risk) with a streaming
Arrow → two-table DuckDB JOIN executed entirely in `post_aggregate`, chunked
per-RESOURCEID group (`requires_cross_chunk_reduction=True`, `chunk_strategy=SINGLE`
per group; ADR-0003 preserved). New path is gated by `DOWNTIME_USE_UNIFIED_JOB`
(default off); legacy Path B stays byte-for-byte untouched (AC-8). Spool schema,
spool key, view endpoints, and frontend are explicit non-goals and must stay
row-identical. This plan defers: any base `chunk_to_duckdb` multi-table
generalization (override in `DowntimeJob` only), the raw two-spool
`query_downtime_dataset_raw` path (out of scope, see design D6), and soak (weekly,
not pre-merge).

## Execution Scope

### In Scope
- New `DowntimeJob` worker + two new DuckDB SQL files (bridge JOIN, cross-shift merge).
- Flag dispatch at route enqueue + worker_fn selection in job service.
- `downtime-unified` job-type registration.
- Env contract for `DOWNTIME_USE_UNIFIED_JOB` (default off, boolean enum).
- Data-shape + business-rules verify-only updates (document both column sets; bridge rule).
- Unit, contract, integration, data-boundary, resilience, stress coverage + stress-soak-report.md.
- `_APPROVED_CALLERS` + job-registry-count test updates (CLAUDE.md rule).

### Out of Scope
- Legacy `_bridge_jobid` Path B body (lines 312-541) — do NOT modify (AC-8).
- `query_downtime_dataset_raw` two-spool / DuckDB-WASM browser-bridge path (design D6).
- Any change to spool schema, spool key, `_SCHEMA_VERSION`, or view endpoints.
- Frontend downtime pages; CSS/UI; API response shape.
- ADR-0003 core decision (no row/time chunking) — preserved, not revisited.
- Base `BaseChunkedDuckDBJob` named-target-table generalization (future work; override locally).

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | env contract | Register `DOWNTIME_USE_UNIFIED_JOB` (default off, boolean enum) in env-contract.md, env.schema.json, .env.example.template, .env.example, CHANGELOG | contract-reviewer |
| IP-2 | data/business contract | Verify-only: assert spool schema unchanged; document both path column sets (D6, no blanket UNCHANGED); add DDA-XX bridge rule if needed | contract-reviewer |
| IP-3 | SQL | New `bridge_join.sql` (D2 RANGE JOIN + window) and `cross_shift_merge.sql` (D3/R3) | backend-engineer |
| IP-4 | worker | New `DowntimeJob`; override `chunk_to_duckdb` (R1); two-kind fan-out; bridge JOIN in `post_aggregate`; register `downtime-unified`; update `_APPROVED_CALLERS` + job-registry count | backend-engineer |
| IP-5 | route+service | Flag dispatch at route enqueue; flag-selected `worker_fn` in job service; legacy Path B unchanged (AC-8) | backend-engineer |
| IP-6 | test plan | Write test-plan.md (AC → test mapping; all families) | test-strategist |
| IP-7 | unit tests | New `tests/test_downtime_unified_job.py` (pre_query, chunk routing, post_aggregate bridge+merge, flag dispatch, spool key) | backend-engineer |
| IP-8 | resilience | E2E/resilience: fault injection, worker restart, spill-to-disk | e2e-resilience-engineer |
| IP-9 | stress | Stress tests + stress-soak-report.md (high-cardinality + single hot RESOURCEID) | stress-soak-engineer |
| IP-10 | ci gates | Confirm flag-path gate wiring; fill ci-gates.md | ci-cd-gatekeeper |
| IP-11 | qa | Release readiness review | qa-reviewer |

## IP Steps (ordered execution)

**IP-1 (contract-reviewer):** Register env flag.
- Files: `contracts/env/env-contract.md`, `contracts/env/env.schema.json`,
  `contracts/env/.env.example.template`, `.env.example`, `contracts/CHANGELOG.md`.
- Add `DOWNTIME_USE_UNIFIED_JOB` row: boolean enum (`on`/`off` or true/false per
  schema convention), default `off`/false. Pin default value, not just name (test-discipline).
- Version entry to `contracts/CHANGELOG.md` only (CLAUDE.md learning).
- Satisfies: AC-6.

**IP-2 (contract-reviewer):** Verify-only data-shape + business rules.
- Files: `contracts/data/data-shape-contract.md`, `contracts/business/business-rules.md`.
- Document the legacy `query_downtime_dataset` bridged-spool column set AND the unified
  job's single bridged-spool column set separately; assert equivalence (no blanket
  "UNCHANGED" — design D6, cache-spool learning). Do NOT conflate with the raw two-spool path.
- Reference BJ-01; add a new DDA-XX bridge-JOIN rule only if RESOURCEID+time-overlap
  winner-selection/80%-ambiguity needs contractual expression beyond BJ-01.
- Satisfies: AC-7 (consistency), AC-1/AC-8 (schema unchanged).

**IP-3 (backend-engineer):** New DuckDB SQL.
- Files: `src/mes_dashboard/sql/downtime_analysis/bridge_join.sql` (new),
  `src/mes_dashboard/sql/downtime_analysis/cross_shift_merge.sql` (new).
- `bridge_join.sql`: per D2 — `JOIN ON base.HISTORYID = job.RESOURCEID AND job.eff_end >
  base.event_start AND job.CREATEDATE < base.event_end`; `overlap_s = epoch(LEAST(...) -
  GREATEST(...))`; `ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY overlap_s DESC,
  CREATEDATE, JOBID)` winner; rn=2 self-compare / `LEAD(overlap_s)` for `match_ambiguous`
  (runner-up ≥80% of winner). RANGE JOIN + window — NOT ASOF (ADR-0010).
- `cross_shift_merge.sql`: 60s-gap walk over `base_raw` grouped by
  `(HISTORYID, OLDSTATUSNAME, OLDREASONNAME)` via LAG/LEAD time-ordered window (R3).
- Satisfies: AC-2 (bridge in DuckDB), AC-7.

**IP-4 (backend-engineer):** New `DowntimeJob`.
- Files: `src/mes_dashboard/workers/downtime_worker.py` (new),
  `src/mes_dashboard/services/job_registry.py` (register),
  `tests/test_query_cost_policy.py` (_APPROVED_CALLERS),
  `tests/test_job_registry.py` (count +1).
- Pattern reference: `eap_alarm_worker.py:285-515` (EapAlarmJob, register call at
  line 519, `execute_eap_alarm_unified_job` 483-515). Base class:
  `base_chunked_duckdb_job.py:73-336` (`chunk_to_duckdb` 152-173, `_fan_out_reduction`
  284-303, `pre_query` 111-117, `build_chunk_sql` 120-129, `post_aggregate` 132-146).
- `DowntimeJob(BaseChunkedDuckDBJob)`: `requires_cross_chunk_reduction=True`,
  `chunk_strategy=SINGLE` per group (D1).
- `pre_query`: resolve candidate RESOURCEID set (DISTINCT HISTORYID, mirror legacy
  `query_downtime_dataset` lines 1220-1235 logic), emit one chunk per RESOURCEID group
  (or small batch) carrying date window.
- `build_chunk_sql`: two kinds per group — `base` (base_events keyed HISTORYID) and
  `job` (job_data keyed RESOURCEID), each its own `chunk_iter` (eap-alarm events/detail split).
- `chunk_to_duckdb` (OVERRIDE — R1): route Arrow batch to `base_raw` vs `job_raw` by
  `chunk_params['kind']`; serialize via `_writer_lock`. Do NOT extend base for named
  tables (deferred — see Deferred/Risks R1).
- `post_aggregate(job_duckdb_path)`: (a) cross-shift merge over `base_raw`, (b) bridge
  JOIN (D2) → winner + match_source/match_ambiguous, (c) `COPY TO` unchanged spool
  parquet, (d) register spool. Preserve spool sort key (R4).
- Register `downtime-unified` job type (reuse `DOWNTIME_WORKER_QUEUE`/TTL constants from
  `downtime_query_job_service.py:30-34`).
- `_APPROVED_CALLERS`: add `downtime_worker` stem to BOTH
  `_APPROVED_CALLERS['oracle_arrow_reader']` AND `['base_chunked_duckdb_job']`.
- `tests/test_job_registry.py`: bump expected `register_job_type()` count by 1.
- Satisfies: AC-2, AC-4, AC-7.

**IP-5 (backend-engineer):** Route + service flag wiring.
- Files: `src/mes_dashboard/routes/downtime_analysis_routes.py` (`api_downtime_query`
  156-303, enqueue site), `src/mes_dashboard/services/downtime_query_job_service.py`.
- Route: resolve `DOWNTIME_USE_UNIFIED_JOB` via `resolve_bool_flag`
  (`core/feature_flags.py:31-49`) at enqueue. ON → enqueue `downtime-unified`; OFF →
  unchanged legacy enqueue (`execute_downtime_query_job` 46-112).
- Job service: flag-selected `worker_fn` dispatch (legacy `execute_downtime_query_job`
  vs `DowntimeJob.run`/`execute_downtime_unified_job`).
- Do NOT touch legacy `_bridge_jobid` Path B body (AC-8). No edit to `feature_flags.py`.
- Satisfies: AC-1 (flag off identical), AC-2, AC-8.

**IP-6 (test-strategist):** Write `test-plan.md`.
- AC → test-file mapping for all 8 ACs; families: unit, contract, integration,
  data-boundary, resilience, stress (soak weekly/out-of-band). Use parity strategy D5
  (schema + rowcount + order-insensitive row-set equality on `(event_id, job_id,
  match_source)`).

**IP-7 (backend-engineer):** Unit tests.
- File: `tests/test_downtime_unified_job.py` (new). Mock `OracleArrowReader.chunk_iter`
  with fixed Arrow batches (D5 unit tier).
- `TestDowntimeJobPreQuery`: RESOURCEID group decomposition.
- `TestDowntimeJobChunkToDb`: base_raw/job_raw routing by `chunk_params['kind']` (R1).
- `TestDowntimeJobPostAggregate`: bridge JOIN winner-selection + `match_ambiguous`
  (two jobs crossing the 80% boundary both directions); cross-shift merge (60s-gap
  fragment pair, both directions per R3); Path-A JOBID hit + orphan.
- `TestDowntimeFlagDispatch`: flag ON/OFF dispatch at route.
- `TestDowntimeJobSpolKey`: spool key invariant unchanged.
- Satisfies: AC-2, AC-3, AC-4, AC-7.

**IP-8 (e2e-resilience-engineer):** Resilience.
- Files: `tests/e2e/test_downtime_analysis_e2e.py` (no-regression, flag default off →
  AC-8), `tests/integration/test_downtime_rq_async.py`.
- Oracle fault injection (one chunk fails mid-JOIN → re-raise, no spool registered, D4);
  worker restart during grouped job; DuckDB spill-to-disk under low-memory.
- Satisfies: AC-5 (spill), AC-8 (no e2e regression).

**IP-9 (stress-soak-engineer):** Stress + report.
- Files: `tests/stress/test_downtime_analysis_stress.py` (extend),
  `specs/changes/downtime-duckdb-join-migration/stress-soak-report.md` (new).
- High-cardinality RESOURCEID × time-overlap JOIN under memory ceiling (no heap OOM, AC-5);
  worst-case single hot RESOURCEID (R2 — grouping does NOT help a hot machine; prove DuckDB
  spill bounds peak RSS).
- Satisfies: AC-5.

**IP-10 (ci-cd-gatekeeper):** Gates.
- Files: `specs/changes/downtime-duckdb-join-migration/ci-gates.md`,
  `contracts/ci/ci-gate-contract.md`. Confirm existing downtime gates wire the new flag
  path; no new workflow expected. Must include literal "workflow"/"promotion policy"/
  "rollback policy" section headers (CLAUDE.md learning).

**IP-11 (qa-reviewer):** Release readiness.
- Files: change dir only. Verify flag-parity evidence, contract pins, stress evidence,
  AC-8 zero-regression standing gate.

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| design.md | D1 (RESOURCEID grouping, reduction flag) | IP-4 chunking model |
| design.md | D2 / ADR-0010 (RANGE JOIN + window, NOT ASOF) | IP-3 bridge SQL |
| design.md | D3 (flag at route enqueue; legacy untouched) | IP-5 dispatch |
| design.md | D4 (connection lifecycle, two-kind fan-out, failure re-raise) | IP-4, IP-8 |
| design.md | D5 (parity: schema+rowcount+row-set equality) | IP-6, IP-7 integration parity |
| design.md | D6 (spool schema unchanged; two column sets documented separately) | IP-2 |
| design.md | R1 (override chunk_to_duckdb), R2 (hot RESOURCEID), R3 (cross-shift SQL fallback), R4 (sort key) | IP-4, IP-3, IP-9 |
| change-classification.md | Inferred AC-1..AC-8 | AC mapping |
| reference_mes_downtime_job_tables.md | RESOURCEID+time-overlap bridge semantics | IP-3, IP-7 fidelity |
| docs/adr/0003 | no row/time chunking | IP-4 chunk strategy |
| docs/adr/0009 / eap_alarm_worker.py:285-515 | BaseChunkedDuckDBJob reference impl | IP-4 |
| test-plan.md (after IP-6) | AC → test mapping | IP-7..IP-9 |
| ci-gates.md (after IP-10) | required gates | verification commands |

## File-Level Plan

| path or glob | action | notes |
|---|---|---|
| src/mes_dashboard/sql/downtime_analysis/bridge_join.sql | create | D2 RANGE JOIN + window (IP-3) |
| src/mes_dashboard/sql/downtime_analysis/cross_shift_merge.sql | create | D3/R3 60s-gap LAG/LEAD (IP-3) |
| src/mes_dashboard/workers/downtime_worker.py | create | DowntimeJob; override chunk_to_duckdb; register downtime-unified (IP-4) |
| src/mes_dashboard/services/job_registry.py | edit | register downtime-unified job type (IP-4) |
| src/mes_dashboard/routes/downtime_analysis_routes.py | edit | flag dispatch in api_downtime_query (156-303) (IP-5) |
| src/mes_dashboard/services/downtime_query_job_service.py | edit | flag-selected worker_fn dispatch (IP-5) |
| src/mes_dashboard/services/downtime_analysis_service.py | do-not-edit | legacy `_bridge_jobid` 312-541 untouched (AC-8); read-only reference for pre_query mirror |
| src/mes_dashboard/core/base_chunked_duckdb_job.py | do-not-edit | override in DowntimeJob; base generalization deferred (R1) |
| src/mes_dashboard/core/feature_flags.py | do-not-edit | use `resolve_bool_flag` 31-49 |
| contracts/env/env-contract.md | edit | add flag row, pin default (IP-1) |
| contracts/env/env.schema.json | edit | boolean enum + default false (IP-1) |
| contracts/env/.env.example.template, .env.example | edit | add flag default off (IP-1) |
| contracts/CHANGELOG.md | edit | version entry (IP-1) |
| contracts/data/data-shape-contract.md | edit | document both column sets (IP-2) |
| contracts/business/business-rules.md | edit | BJ-01 ref + optional DDA-XX (IP-2) |
| tests/test_downtime_unified_job.py | create | unit tier (IP-7) |
| tests/test_query_cost_policy.py | edit | add `downtime_worker` to both _APPROVED_CALLERS (IP-4) |
| tests/test_job_registry.py | edit | count +1 (IP-4) |
| tests/e2e/test_downtime_analysis_e2e.py | edit | no-regression (IP-8) |
| tests/integration/test_downtime_rq_async.py | edit | flag parity + resilience (IP-8) |
| tests/stress/test_downtime_analysis_stress.py | edit | high-cardinality + hot RESOURCEID (IP-9) |
| specs/changes/downtime-duckdb-join-migration/stress-soak-report.md | create | IP-9 |
| specs/changes/downtime-duckdb-join-migration/test-plan.md | edit | IP-6 |
| specs/changes/downtime-duckdb-join-migration/ci-gates.md | edit | IP-10 |

## Contract Updates

- API: none (response shape verify-only; unchanged).
- CSS/UI: none.
- Env: add `DOWNTIME_USE_UNIFIED_JOB` (default off, boolean enum + default false) to
  env-contract.md, env.schema.json, .env.example.template, .env.example; contract test
  pins name + default (IP-1, AC-6).
- Data shape: verify-only — document legacy bridged-spool columns AND unified bridged-spool
  columns separately; assert equivalence; do NOT conflate with raw two-spool path (IP-2, D6).
- Business logic: verify-only — RESOURCEID+time-overlap bridge stays consistent with BJ-01 /
  reference_mes_downtime_job_tables.md; add DDA-XX only if needed (IP-2, AC-7).
- CI/CD: none expected — confirm existing downtime gates wire the flag path (IP-10).

## Test Execution Plan

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | tests/integration/test_rowcount_flag_parity.py | flag off output byte/row-identical to baseline |
| AC-2 | tests/test_downtime_unified_job.py::TestDowntimeJobPostAggregate | bridge JOIN runs in DuckDB; no pd.merge in new path |
| AC-3 | tests/integration/test_downtime_rq_async.py | flag-on vs flag-off spool parquet row-set equal (D5) |
| AC-4 | tests/test_downtime_unified_job.py::TestDowntimeJobPreQuery | per-RESOURCEID SINGLE chunks; no TIME/ROW_COUNT chunking |
| AC-5 | tests/stress/test_downtime_analysis_stress.py | completes via spill, no heap OOM under memory ceiling |
| AC-6 | tests/test_env_contract.py | DOWNTIME_USE_UNIFIED_JOB name + default off pinned |
| AC-7 | tests/test_downtime_unified_job.py::TestDowntimeJobPostAggregate | winner-selection + match_ambiguous + cross-shift merge correct |
| AC-8 | tests/e2e/test_downtime_analysis_e2e.py | downtime flow unchanged with flag default off |

(`cdd-kit test select` falls back to this table only when test-plan.md has no mapping;
test-plan.md (IP-6) is the authoritative mapping. Required floor: collect, targeted,
changed-area; full ladder in test-plan.md / references/sdd-tdd-policy.md.)

## Bounded Test Ladder

- collect: `cdd-kit test run --phase collect` — collect-only tests/test_downtime_unified_job.py,
  tests/integration/test_downtime_rq_async.py, tests/integration/test_rowcount_flag_parity.py,
  tests/contract/, tests/test_env_contract.py (verify import/collection, no execution).
- targeted: `cdd-kit test run --phase targeted` — run new tests/test_downtime_unified_job.py only.
- changed-area: `cdd-kit test run --phase changed-area` — all downtime tests
  (tests/test_downtime_unified_job.py, tests/integration/test_downtime_rq_async.py,
  tests/integration/test_rowcount_flag_parity.py, tests/e2e/test_downtime_analysis_e2e.py)
  plus tests/test_base_chunked_duckdb_job.py, tests/test_job_registry.py,
  tests/test_query_cost_policy.py.
- contract: `cdd-kit validate --contracts` + env-flag contract test (tests/test_env_contract.py).
  Requires `pip install jsonschema` (CLAUDE.md learning).
- (stress AC-5 runs weekly/manual, not in the pre-merge floor — see test-plan.md.)

## Non-Goals Confirmed

- No frontend downtime page changes (spool schema unchanged).
- ADR-0003 core decision (cross-row aggregation, no row/time chunking) not changed.
- Legacy `_bridge_jobid` Path B `pd.merge` body NOT deleted/modified while flag exists (AC-8).
- `query_downtime_dataset_raw` raw two-spool / DuckDB-WASM path out of scope (D6).
- No spool key / `_SCHEMA_VERSION` bump; no view-endpoint or API response change.

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.

## Deferred / Risks

- R1 (high): two-table fan-out under `requires_cross_chunk_reduction=True`. The base
  `chunk_to_duckdb` (base_chunked_duckdb_job.py:152-173) infers ONE `raw` table.
  Decision (planner): OVERRIDE `chunk_to_duckdb` in `DowntimeJob` to route by
  `chunk_params['kind']` → `base_raw`/`job_raw`; do NOT generalize the base now. Flag base
  named-target-table support as future work.
- R2 (medium): DuckDB inequality-JOIN candidate fan-out is large for a single hot
  RESOURCEID — per-group chunking does not shrink it; the win is on-disk spill. IP-9 must
  exercise worst-case single high-volume RESOURCEID and confirm spill bounds peak RSS.
- R3 (medium): cross-shift merge fidelity in SQL. Backend-engineer DECISION POINT during
  IP-3/IP-4: attempt the SQL form (LAG/LEAD over time-ordered events grouped by
  `(HISTORYID, OLDSTATUSNAME, OLDREASONNAME)`) FIRST. If the 60s-gap walk cannot be made
  byte-faithful (verify against the D5 fragment-pair parity test in BOTH directions),
  FALL BACK to keeping `_merge_cross_shift_events` in pandas over the already-reduced
  per-group `base_raw`, and move ONLY the bridge JOIN to DuckDB. Record the chosen path in
  the agent-log and (if fallback) note it in ADR-0010 / design follow-up. Either way the
  N×M Cartesian (Path B `pd.merge`) MUST leave Python.
- R4 (low): preserve `base_events` ORDER BY vs BQE-03 spool sort key (ADR-0003 consequence
  #3); verify the unified job's spool sort key matches legacy in IP-7/IP-8.

## Known Risks

- Parity is the gating risk: winner-selection (overlap-magnitude ranking) and the 80%
  ambiguity flag move from pandas to DuckDB SQL — a count-only test would pass while
  silently regressing. Enforce full row-set equality (D5) in IP-7/IP-8.
- ASOF-JOIN substitution is a silent-regression trap (ADR-0010); bridge_join.sql must use
  RANGE JOIN + window function only.
- test-plan.md and ci-gates.md are still scaffolds at planning time; IP-6 and IP-10 must
  fill them before the gate. ci-gates.md must carry literal "workflow"/"promotion policy"/
  "rollback policy" headers or `cdd-kit gate` fails.
- `.cdd/code-map.yml` was read for all pointers above; if it has gone stale, re-run
  `cdd-kit code-map` before trusting the line ranges.
