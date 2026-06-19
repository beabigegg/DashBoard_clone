---
change-id: material-trace-streaming-migration
schema-version: 0.1.0
last-changed: 2026-06-19
---

# Implementation Plan: material-trace-streaming-migration

## Objective

Behind feature flag `MATERIAL_TRACE_USE_UNIFIED_JOB` (default `off`), route material-trace
heavy queries onto the unified `BaseChunkedDuckDBJob` streaming pipeline (Oracle → Arrow →
DuckDB/parquet spool) instead of the `pd.concat(chunks)` + post-hoc `_check_memory_guard()`
path. Flag `off` leaves the legacy path byte-identical. Flag `on` always-async (202; 503 when
RQ/Redis unavailable, no sync fallback). Spool namespace `material_trace` and parquet schema
stay identical so the frontend `/view`+CSV path is untouched. See design.md D1–D4.

## Execution Scope

### In Scope
- New `MaterialTraceJob(BaseChunkedDuckDBJob)` in `material_trace_duckdb_runtime.py` (design.md "Affected Components").
- Flag branch in `material_trace_service.py` / `material_trace_routes.py` query handler.
- Env + business-rules contract updates; CHANGELOG bumps.
- Unit + contract tests for AC-1, AC-2, AC-3, AC-4(schema-equiv), AC-6, AC-7, AC-8, flag default-off.

### Out of Scope
- Frontend material-trace pages (spool schema unchanged — non-goal).
- downtime migration (separate change).
- Any code change to `core/global_concurrency.py` mechanics (D3: semantics-only doc update).
- Any change to `core/base_chunked_duckdb_job.py` (consumed unchanged — design.md, classification Assumption).
- New API endpoint / response-shape / data-shape contract change (classification: none expected).

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | env contract | add `MATERIAL_TRACE_USE_UNIFIED_JOB` to env-contract.md + env.schema.json + .env.example.template | backend-engineer |
| IP-2 | business-rules | add semaphore-role rule (D3) + 3 flag-behavior rows (D4); bump version + CHANGELOG | backend-engineer |
| IP-3 | job class | create `MaterialTraceJob(BaseChunkedDuckDBJob)` (pre_query / build_chunk_sql / post_aggregate) | backend-engineer |
| IP-4 | RQ entry + register | add unified worker entry fn + `register_job_type("material-trace-unified", ...)` | backend-engineer |
| IP-5 | route dispatch | flag branch in query handler: on→202/503, off→legacy unchanged | backend-engineer |
| IP-6 | guard removal | unified path never calls `_check_memory_guard()` (D2) | backend-engineer |
| IP-7 | unit/contract tests | AC-1/2/3/4/6/7/8 + flag default-off | test-strategist |
| IP-8 | CHANGELOG | bump contracts/CHANGELOG.md + contracts/ci/ci-gate-contract.md note | backend-engineer / ci-cd-gatekeeper |

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| design.md | D1 (no cross-chunk reduction; 4-col DISTINCT key) | post_aggregate dedup |
| design.md | D2 (remove post-hoc guard) | IP-6 |
| design.md | D3 (semaphore re-purpose, no code change) | IP-2 |
| design.md | D4 (503, no sync fallback) | IP-5 |
| design.md | Open Risks (dedup key / WORKCENTER_GROUP / Decimal coercion / spool key) | IP-3 must-handle |
| change-classification.md | AC-1..AC-8 | acceptance mapping |
| test-plan.md | AC→test mapping, ladder | tests to run/write |
| ci-gates.md | Required Gates + Rollback Policy | verification commands |
| contracts/env/env-contract.md L81–84 | existing `*_USE_UNIFIED_JOB` rows | IP-1 row format |
| contracts/business/business-rules.md L251–259 | existing flag-behavior rows | IP-2 row format |
| contracts/ci/ci-gate-contract.md L502–524 | resource-history-migration note | IP-8 pattern |

## File-Level Plan

| path or glob | action | notes |
|---|---|---|
| contracts/env/env-contract.md | edit | add `MATERIAL_TRACE_USE_UNIFIED_JOB` row matching L81–84 format (feature, all, default `off`, restart req.) |
| contracts/env/env.schema.json | edit | add property with `enum`+`default` (env test-discipline rule) |
| contracts/env/.env.example.template | edit | add `MATERIAL_TRACE_USE_UNIFIED_JOB=off` (after L34) |
| contracts/business/business-rules.md | edit | new semaphore-role rule (D3) + 3 flag rows (D4); bump schema-version |
| contracts/CHANGELOG.md | edit | env + business-rules entries |
| contracts/ci/ci-gate-contract.md | edit | gate-compat note (no new gate); bump ci schema-version + CHANGELOG |
| src/mes_dashboard/core/feature_flags.py | edit | register flag read helper (mirror existing `*_USE_UNIFIED_JOB`) |
| src/mes_dashboard/services/material_trace_duckdb_runtime.py | edit | add `MaterialTraceJob(BaseChunkedDuckDBJob)` (IP-3) |
| src/mes_dashboard/services/material_trace_service.py | edit | unified worker entry fn + `register_job_type` (IP-4); keep legacy fns for flag=off |
| src/mes_dashboard/routes/material_trace_routes.py | edit | flag branch in `api_material_trace_query` (IP-5) |
| tests/test_material_trace_unified_job.py | create | AC-1/2/3/4/6/8 + flag default-off |
| tests/contract/test_env_material_trace_flag.py | create | AC-7 env default pin (mirror eap-alarm flag test) |

## Ordered Steps

- **IP-1 — Env contract + schema.** Add `MATERIAL_TRACE_USE_UNIFIED_JOB` (feature, all envs, optional, default `off`, restart-required; enum `off/on/false/true/0/1`) to all three env files. env.schema.json entry MUST carry `enum`+`default` (entries absent from schema bypass machine validation). Satisfies AC-7. (Files: env-contract.md, env.schema.json, .env.example.template.)
- **IP-2 — Business-rules contract.** Add a rule documenting the heavy-query semaphore (`global_concurrency.acquire_heavy_query_slot`, `HEAVY_QUERY_MAX_CONCURRENT` default 3) role as "cap concurrent RQ heavy jobs hitting Oracle" — explicitly **no code change** (D3). Add 3 flag-behavior rows mirroring L251–259: on+async→202; on+no RQ→503 (no sync fallback, D4); off→legacy path unchanged. Bump schema-version + add CHANGELOG entry. Satisfies AC-7. (Files: business-rules.md, CHANGELOG.md.)
- **IP-3 — `MaterialTraceJob` class.** Add subclass to `material_trace_duckdb_runtime.py`:
  - `chunk_strategy = ChunkStrategy.ID_LIST`; `requires_cross_chunk_reduction = False` (D1).
  - `namespace = "material_trace"` — MUST match the legacy spool namespace; confirm against `_mt_spool_id` (service L530–532) / `make_route_query_hash` (L800–816). Do not invent a new namespace (spool-key determinism risk).
  - `pre_query`: parse params, resolve container/lot IDs via the same `_resolve_container_ids` (L146–172) the legacy path uses, compute `query_id` via `make_route_query_hash` (D-risk: spool key determinism), decompose IDs into 1000/batch (`decompose_by_ids`; matches legacy `_IN_BATCH_SIZE=1000`). AC-8.
  - `build_chunk_sql`: per-batch Oracle SELECT for one ≤1000-ID IN-list — same SQL as legacy `_execute_batched_query` per-batch query (L191–240). Reproduce the Decimal→float coercion the legacy parquet path applies (L302) so dtypes match at parity (D-risk: Decimal/CHAR coercion).
  - `post_aggregate`: DuckDB `SELECT DISTINCT` on the **exact** 4-col key `[CONTAINERID, MATERIALLOTNAME, WORKCENTERNAME, TXNDATE]` (legacy L237–238) → COPY TO spool parquet. Apply `_enrich_workcenter_group` (WORKCENTER_GROUP) inside this DuckDB stage so spool columns match the legacy spool schema — verify the full column **set+order**, not just rowcount (D-risk: enrichment placement). A wider/narrower DISTINCT key silently changes rowcount (D-risk: dedup fidelity).
  Satisfies AC-4, AC-8 (and AC-5 structurally via streaming/spill).
- **IP-4 — RQ entry function + register.** In `material_trace_service.py`, add `execute_material_trace_unified_job(job_id, **params)` that instantiates and runs `MaterialTraceJob`, and `register_job_type("material-trace-unified", JobTypeConfig(...))` at module bottom (mirror existing `register_job_type` at L951; the legacy `rq_material_trace_job` L919–945 stays for flag=off). Use `importlib.reload()`-compatible registration (test-discipline). Satisfies AC-2.
- **IP-5 — Route dispatch.** In `material_trace_routes.py` `api_material_trace_query` (L125–199): read `MATERIAL_TRACE_USE_UNIFIED_JOB` as a module-level constant. If flag=on → check `is_async_available()`; if False → return 503 SERVICE_UNAVAILABLE (no silent fallback, D4); else `enqueue_job("material-trace-unified", ...)` and return 202. If flag=off → existing legacy path unchanged. Satisfies AC-2, AC-3, AC-1.
- **IP-6 — Remove post-hoc guard from unified path.** The unified path (IP-3/IP-4) MUST NOT call `_check_memory_guard()` (legacy L175–188, called at L239 after concat) — DuckDB on-disk spill is the structural replacement (D2). The function and its legacy callsites stay for flag=off. Prove absence by AST-walk over the unified worker/job module (`ast.parse` + walk `ast.Call`, test-discipline). Satisfies AC-6.
- **IP-7 — Unit + contract tests.** See Test Execution Plan + test-plan.md. AC-1 legacy-path-unchanged (flag-off uses `pd.concat`); AC-2 flag-on enqueues "material-trace-unified"; AC-3 flag-on + no RQ → 503; AC-4 spool schema-equivalence flag-off vs flag-on; AC-6 ast-walk guard removed; AC-7 env default pin; AC-8 1000/batch decomposition; flag default-off assertion via `monkeypatch.setattr` (module-level constant). (Owner: test-strategist.)
- **IP-8 — Contract CHANGELOG bumps.** Bump `contracts/CHANGELOG.md` (env + business-rules) and `contracts/ci/ci-gate-contract.md` (gate-compat note: no new gate; flag default-off; bump ci schema-version + CHANGELOG), mirroring the resource-history-migration note (L502–524).

## Contract Updates

- API: none (no endpoint/response-shape change; contract-reviewer confirms — classification).
- CSS/UI: none.
- Env: `MATERIAL_TRACE_USE_UNIFIED_JOB` added to env-contract.md + env.schema.json (enum+default) + .env.example.template (IP-1).
- Data shape: none — spool parquet schema unchanged (AC-4; contract-reviewer confirms).
- Business logic: semaphore-role rule (D3) + 3 flag rows (D4) in business-rules.md (IP-2).
- CI/CD: no new gate; additive gate-compat note in ci-gate-contract.md (IP-8).

## Test Execution Plan

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | tests/test_material_trace_unified_job.py | flag-off → legacy `pd.concat` path; result identical |
| AC-2 | tests/test_material_trace_unified_job.py | flag-on → enqueues "material-trace-unified" job |
| AC-3 | tests/test_material_trace_unified_job.py | flag-on + no RQ → HTTP 503, no sync fallback |
| AC-4 | tests/test_material_trace_unified_job.py | flag-off vs flag-on spool parquet column set+order+types equal |
| AC-6 | tests/test_material_trace_unified_job.py | ast-walk: no `_check_memory_guard` call on unified path |
| AC-7 | tests/contract/test_env_material_trace_flag.py | env default pinned to `off` |
| AC-8 | tests/test_material_trace_unified_job.py | ID-list >1000 decomposes at 1000/batch |
| flag default-off | tests/test_material_trace_unified_job.py | constant resolves `off` when unset |

(Selector floor: collect, targeted, changed-area. Full ladder + family matrix in test-plan.md;
policy in references/sdd-tdd-policy.md. Resilience deferred nightly, stress/soak deferred weekly.)

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.
- Do NOT modify `core/base_chunked_duckdb_job.py` or `core/global_concurrency.py` mechanics (consumed unchanged).

## Known Risks

- **Dedup-key fidelity (D1/Open Risks):** post_aggregate DISTINCT must use exactly `[CONTAINERID, MATERIALLOTNAME, WORKCENTERNAME, TXNDATE]`; wider/narrower key changes rowcount vs legacy. Pin with AC-4 parity test.
- **WORKCENTER_GROUP enrichment placement:** must enrich inside the DuckDB/chunk stage so spool columns match legacy schema; verify column set+order, not just rowcount.
- **Decimal→float / CHAR coercion:** Arrow path must reproduce legacy parquet dtype coercion (service L302) or parity check drifts.
- **Spool-key determinism:** unified path must keep `make_route_query_hash` as the spool key so frontend `query_id` reuse + spool-hit idempotency survive.
- **Module-level flag drift:** flag is a constant frozen at boot; gunicorn + worker must read the same value (resource-history-migration deploy note). Test with `monkeypatch.setattr`, not `setenv`.
- **code-map currency:** `.cdd/code-map.yml` generated 2026-06-19 (current); line refs above sourced from it.
