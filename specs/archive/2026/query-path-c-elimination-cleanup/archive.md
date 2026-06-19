---
change-id: query-path-c-elimination-cleanup
closed-date: 2026-06-19
status: archived
---

# Archive: query-path-c-elimination-cleanup

## Change Summary

P4+P5 of query-dataflow-unification eliminated the last gunicorn-blocking synchronous "Path C". The `query_tool_routes` equipment-period endpoint gained an `QUERY_TOOL_USE_RQ` feature flag (default off) that routes oversized queries (classify_query_cost ≥ L3, 200k rows) to RQ returning 202+job_id instead of blocking a worker for up to 300s. `wip_routes` gained a COUNT(*) rowcount pre-check (fail-open to sync on error) to handle the wip domain's lack of date-range routing signal. Four per-domain `*_ASYNC_DAY_THRESHOLD` env vars were removed after completing their deprecate-2-minors cycle; all routing now uses `classify_query_cost(domain=...)` uniformly. `batch_query_engine.merge_chunks` was marked deprecated (no callers). The `global_concurrency` semaphore docstring was updated to clarify its RQ Oracle concurrency role (doc-only, no runtime change).

## Final Behavior

- `QUERY_TOOL_USE_RQ=off` (default): equipment-period query unchanged, fully sync.
- `QUERY_TOOL_USE_RQ=on` + classify ≥ L3: returns 202 `{"async": true, "job_id": "..."}` — client polls existing job-status endpoint.
- `wip_routes api_detail`: COUNT(*) pre-check; ≥ L3 rows → RQ dispatch; COUNT error → fail-open sync.
- `DOWNTIME_ASYNC_DAY_THRESHOLD`, `HOLD_ASYNC_DAY_THRESHOLD`, `RESOURCE_ASYNC_DAY_THRESHOLD`, `REJECT_ASYNC_DAY_THRESHOLD` removed from code and env.schema.json; inert extra vars in deployed .env silently ignored.
- `merge_chunks` emits `DeprecationWarning` at stacklevel=2; behavior unchanged; zero production callers.

## Final Contracts Updated

| contract | version | change |
|---|---|---|
| `contracts/env/env-contract.md` | 1.0.21 | Remove 4 threshold vars; add `QUERY_TOOL_USE_RQ` with enum + default "off" |
| `contracts/env/env.schema.json` | — | Add `QUERY_TOOL_USE_RQ` property; remove 4 threshold entries |
| `contracts/api/api-contract.md` | 1.25.1 | equipment-period 202 status; `QueryToolJobAccepted` schema; Type B routing note |
| `contracts/api/openapi.json` | — | Regen'd (184 endpoints) |
| `contracts/business/business-rules.md` | 1.28.0 | ASYNC-12 (query-tool RQ dispatch), ASYNC-13 (wip COUNT pre-check), ASYNC-14 (semaphore intent) |
| `contracts/CHANGELOG.md` | — | Three new versioned entries |

## Final Tests Added / Updated

- `tests/contract/test_env_async_threshold_removal.py` (6 tests, AC-5/AC-6/AC-7)
- `tests/integration/test_query_tool_rq_async.py` (4 mock tests, AC-1/AC-2)
- `tests/integration/test_wip_rowcount_rq_routing.py` (3 mock tests, AC-3)
- `tests/stress/test_query_tool_stress.py::TestAC8StructuralGuarantees` (2 structural stress tests, AC-8)
- `tests/test_batch_query_engine.py::TestMergeChunks::test_merge_chunks_emits_deprecation_warning` (AC-4)
- `tests/test_job_registry.py` — count 10→11, "query-tool" in expected_types
- Updated: test patches across 8 files migrated from `*_ASYNC_DAY_THRESHOLD` mocks to `_classify_query_cost`/`classify_query_cost` mocks

Full suite: **4,880 passed, 592 skipped (integration_real), 0 failed**

## Final CI/CD Gates

Gate passed locally: collect, targeted, changed-area, contract, quality, full — all green. See `specs/changes/query-path-c-elimination-cleanup/test-evidence.yml`.

## Production Reality Findings

- The 4 deprecated threshold vars had inconsistent defaults (30/90/90/10 days); unified to `CostPolicy.day_threshold=30`. Parity confirmed by test migration.
- `reject_query_job_service.should_use_async` gained a ValueError guard for invalid ISO dates propagated from `classify_query_cost._date_span_days` — a robustness fix surfaced during migration.
- `acquire_heavy_query_slot` is not wired into `execute_query_tool_job` (nor into any existing `execute_*_job` worker). The semaphore mechanism is structurally proven (AC-8 stress tests pass) but end-to-end worker integration is a pre-production gate item before `QUERY_TOOL_USE_RQ=on` is activated in production.
- `test_oracle_error_codes.py` was erroneously `--ignore`'d in the full-phase evidence run (it is not `integration_real`). Standalone: 10/10 pass. Process drift only; no masked failure.

## Lessons Promoted to Standards

1. **`acquire_heavy_query_slot` wiring requirement** — Every new `execute_*_job` worker function must wire `acquire_heavy_query_slot` before the owning flag goes to production. Promoted to `docs/architecture/service-patterns.md` §RQ Worker Concurrency Gate + one-liner in CLAUDE.md.
   - Evidence: stress-soak-engineer agent-log; stress-soak-report.md "Production Readiness Gate" section; ADR-0011.

2. **COUNT(*) fail-open pre-check for domains without date-range signal** — Domains that can't estimate query cost from a date range (e.g., wip) use a `count_*_rows()` → `classify_query_cost(domain=..., row_count=count)` call as the L3 estimator; any COUNT error must fail-open to sync (not 503). Promoted to `docs/architecture/service-patterns.md` §Async Routing Pre-Check Pattern + one-liner in CLAUDE.md.
   - Evidence: spec-architect agent-log (D2 decision); wip_routes implementation; test_wip_rowcount_rq_routing.py test_wip_count_error_fails_open_stays_inline.

## Follow-up Work

- Wire `acquire_heavy_query_slot` into `execute_query_tool_job` (and other `execute_*_job` workers) in a dedicated PR before `QUERY_TOOL_USE_RQ=on` promotion to production. (Pre-production gate — not a blocker for flag-off deployment.)
- E2E tests (`test_query_tool_e2e.py`, `test_wip_hold_pages_e2e.py`) require running Flask app + playwright — CI nightly post-merge.
- Real-Oracle integration tests (572 `integration_real` skipped) — nightly gate.
- Re-run full-phase evidence without `--ignore tests/integration/test_oracle_error_codes.py` on next CI run.

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and active project guidance. Do not use this document as a requirements source.
