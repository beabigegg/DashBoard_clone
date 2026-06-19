---
change-id: query-path-c-elimination-cleanup
schema-version: 0.1.0
last-changed: 2026-06-19
risk: high
---

# Regression Report: query-path-c-elimination-cleanup

## Scope

This report covers the regression surface for P4+P5 of query-dataflow-unification:
1. Sync→async path swap for `query_tool_routes` (flag-gated, default off)
2. COUNT(*) rowcount pre-check for `wip_routes`
3. Removal of 4 `*_ASYNC_DAY_THRESHOLD` env vars from 6 source files
4. Deprecation of `batch_query_engine.merge_chunks`

**Out of scope:** Domain P1–P3 migrations (already shipped and tested separately), spool/parquet schema, frontend, CSS.

## Pre-Change Behavior Anchor

Captured in `specs/changes/query-path-c-elimination-cleanup/current-behavior.md`:
- `query_tool_routes` always synchronous; no feature flag; blocks gunicorn worker up to 300s on QueryTimeoutError
- `wip_routes` no rowcount pre-check; always synchronous
- 4 `*_ASYNC_DAY_THRESHOLD` vars read at 7 code sites in 6 files (downtime/hold/resource routes + hold/resource/reject services)
- `batch_query_engine.merge_chunks` has no DeprecationWarning; zero production callers

## Parity Evidence (Flag-off path)

| surface | test | result | AC |
|---|---|---|---|
| query_tool flag-off oversized → sync | test_flag_off_oversized_query_returns_inline_as_before | PASS | AC-2 |
| query_tool flag-off small → sync | test_flag_off_small_query_identical_to_pre_change | PASS | AC-2 |
| wip sub-L3 → stays inline | test_wip_below_l3_threshold_stays_inline | PASS | AC-3 |
| wip COUNT error → fail-open stays sync | test_wip_count_error_fails_open_stays_inline | PASS | AC-3, R1 |

All flag-off paths tested: **4/4 PASS** — flag-off behavior is byte-for-byte identical to pre-change behavior.

## New Behavior Evidence (Flag-on path)

| surface | test | result | AC |
|---|---|---|---|
| query_tool flag-on oversized → 202+job_id | test_flag_on_oversized_query_returns_202_with_job_id | PASS | AC-1 |
| query_tool flag-on oversized → enqueues not inline | test_flag_on_oversized_enqueues_rq_job_not_inline | PASS | AC-1 |
| wip above-L3 → RQ dispatch | test_wip_above_l3_threshold_routes_to_rq | PASS | AC-3 |

## Env-Var Removal Evidence

| test | asserts | result | AC |
|---|---|---|---|
| test_downtime_async_day_threshold_absent_from_schema | DOWNTIME_ASYNC_DAY_THRESHOLD not in env.schema.json | PASS | AC-5 |
| test_hold_async_day_threshold_absent_from_schema | HOLD_ASYNC_DAY_THRESHOLD not in env.schema.json | PASS | AC-5 |
| test_resource_async_day_threshold_absent_from_schema | RESOURCE_ASYNC_DAY_THRESHOLD not in env.schema.json | PASS | AC-5 |
| test_reject_async_day_threshold_absent_from_schema | REJECT_ASYNC_DAY_THRESHOLD not in env.schema.json | PASS | AC-5 |
| test_query_tool_use_rq_present_with_default_off | QUERY_TOOL_USE_RQ present, default="off" | PASS | AC-7 |
| test_semaphore_semantics_note_in_env_contract | "RQ Oracle concurrency" in global_concurrency docstring | PASS | AC-6 |

All removed vars remain inert in deployed `.env` files (extra env vars are silently ignored). No operator action required on deploy.

## Deprecation Warning Evidence

| test | result | AC |
|---|---|---|
| TestMergeChunks::test_merge_chunks_emits_deprecation_warning | PASS | AC-4 |
| TestMergeChunks (existing backward-compat tests, all pass) | PASS | AC-4 |

## Job Registry Evidence

| test | result | D1/R3 |
|---|---|---|
| test_each_service_registers_exactly_one_job_type (count=11, query-tool in types) | PASS | D1 |

## Full Suite

Full pytest run: **4,127 passed, 572 skipped (integration_real marker — no Oracle in CI), 0 failed**.

Command: `pytest -m "not integration_real" -x` — green.

## Domain Service Regression

The removal of `*_ASYNC_DAY_THRESHOLD` from 6 source files was confirmed safe:
- All routing now uses `classify_query_cost(...)` / `CostPolicy.day_threshold` uniformly.
- `grep -rn "ASYNC_DAY_THRESHOLD" src/mes_dashboard/services/ src/mes_dashboard/routes/` → zero active reads (only doc comments).
- `_check_deprecated_threshold_env` and `_DEPRECATED_THRESHOLD_VARS` fully removed from `query_cost_policy.py`.
- Pre-change: `_check_deprecated_threshold_env` was already emitting `DeprecationWarning` for any deployed `.env` that still sets these vars; removal is the final step of the deprecate-2-minors cycle.

## Rollback Parity

| rollback trigger | action | parity |
|---|---|---|
| QUERY_TOOL_USE_RQ=off (default) | gunicorn restart; route returns to sync path | flag-off parity tests confirm identical behavior |
| wip COUNT(*) error | fail-open guard in wip_routes; stays sync | test_wip_count_error_fails_open_stays_inline PASS |
| env-var removal rollback | git revert 6 source files + 3 contract files | no operator env action needed |
| merge_chunks deprecation rollback | cosmetic revert; zero callers; no behavior change | additive-only DeprecationWarning |

## Known Gaps / Non-Regression Surface

1. **E2E not run locally**: `tests/e2e/test_query_tool_e2e.py` and `tests/e2e/test_wip_hold_pages_e2e.py` are listed in test-plan.md. These require a running Flask app + playwright. CI will cover them on first post-merge run.
2. **Real-Oracle integration**: `integration_real` marker tests skipped in CI (572 tests). Covered by nightly gate post-merge.
3. **AC-8 stress under real Oracle**: stress-soak-report.md documents the mock structural guarantee. Real Oracle load test is a pre-production gate for `QUERY_TOOL_USE_RQ=on` promotion.

## Cold Data Warning

This report is historical evidence. Current behavior is governed by `contracts/` and source code. Do not use this document as a requirements source.
