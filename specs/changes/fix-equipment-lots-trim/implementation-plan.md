---
change-id: fix-equipment-lots-trim
schema-version: 0.1.0
last-changed: 2026-07-09
---

# Implementation Plan: fix-equipment-lots-trim

## Objective
Complete the backend half of the four-part fix so the query-tool "批次追蹤生產設備"
生產紀錄 (production-records) sub-tab renders non-empty rows: (1) TRIM Oracle
CHAR-padding off `CONTAINERNAME` in `equipment_lots.sql`, and (2) add an optional
server-side `container_names` narrowing filter to `get_equipment_lots()`, wired
identically through the sync route and the async RQ job. Then regenerate the two
openapi mirrors and confirm `cdd-kit validate` is green.

Frontend and contracts are already done (see Out of Scope). This plan is the
execution packet for **backend-engineer**.

## Execution Scope

### In Scope
- SQL TRIM fix + new `CONTAINER_FILTER` placeholder in `equipment_lots.sql`.
- `get_equipment_lots()` optional `container_names` param + `UPPER(TRIM(...)) IN (...)` filter.
- Sync route (`query_equipment_period`) body parse + forwarding, incl. async `_params` parity.
- Async worker branch (`execute_query_tool_job`, `query_sub_type=='lots'`) forwarding.
- Backend tests per test-plan.md AC mapping (unit, contract-route, integration parity).
- Final: regenerate `contracts/openapi.json` + `contracts/api/openapi.json`, run `cdd-kit validate`.

### Out of Scope
- Frontend `useLotEquipmentQuery.ts` `.trim()` fix + `frontend/tests/query-tool/useLotEquipmentQuery.test.js` — **already DONE** (3 tests green).
- `contracts/api/api-contract.md` (schema-version 1.38.2→1.38.3 + Compatibility Notes) and `contracts/CHANGELOG.md` — **already DONE**, contract-reviewer approved. Do not re-edit prose.
- CSV export path (`_format_equipment_lots_export_rows`) — no `container_names` wiring (test-plan.md Out of Scope).
- `materials`/`jobs`/`rejects`/`status_hours` sub-types — `container_names` is `lots`-only (AC-4 scope).
- Any refactor of `QueryBuilder`, pagination, or unrelated equipment queries.

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | SQL | `equipment_lots.sql:31` `c.CONTAINERNAME,` → `TRIM(c.CONTAINERNAME) AS CONTAINERNAME,`; add `AND {{ CONTAINER_FILTER }}` after line 42 `AND {{ EQUIPMENT_FILTER }}` in the same WHERE; document the new placeholder in header comment (lines 8-9) | backend-engineer |
| IP-2 | service | `get_equipment_lots()` (2430-2500): add kwarg-only `container_names: Optional[List[str]] = None`; build `CONTAINER_FILTER` on the same builder via the `_build_two_filters` dual-builder pattern with `UPPER(TRIM(c.CONTAINERNAME))` col expr and uppercased+stripped values; pass `CONTAINER_FILTER=` into `SQLLoader.load_with_params`; empty/absent → `1=1` | backend-engineer |
| IP-3 | route | `query_equipment_period()` (655-781): read `container_names = data.get('container_names') or []` (~674); add `container_names=container_names,` to async `_params` dict (707-718); pass `container_names=container_names` into `query_type=='lots'` `get_equipment_lots(...)` (747-753) | backend-engineer |
| IP-4 | worker | `execute_query_tool_job()` (2882-2894): in `query_sub_type=='lots'` branch read `container_names = query_params.get("container_names") or []` and add `container_names=container_names` to the `get_equipment_lots(...)` call (line 2894) | backend-engineer |
| IP-5 | tests | Add backend tests per test-plan.md AC→test mapping (unit + route contract + integration parity incl. `inspect.signature(...).bind()`) | backend-engineer |
| IP-6 | openapi mirrors | `cdd-kit openapi export --out contracts/openapi.json` and `--out contracts/api/openapi.json`; then `cdd-kit validate` green | backend-engineer |

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| test-plan.md | AC→Test Mapping table + Notes (fixture shape, `mock_load.call_args.kwargs`, worker signature check) | tests to write/run (IP-5) |
| test-plan.md | Test Execution Ladder | required phases: collect, targeted, changed-area, contract, full |
| ci-gates.md | Required Gates table + "Blocking finding" (lines 52-60) | gates + mandatory openapi-mirror regeneration (IP-6) |
| change-classification.md | Inferred Acceptance Criteria AC-1..AC-7 | acceptance mapping |
| contracts/api/api-contract.md | `POST /api/query-tool/equipment-period` row (already at 1.38.3) | endpoint shape (read-only, do not edit) |
| contracts/business/business-rules.md | QT-05/QT-06 | read-only: partial-trackout aggregation unchanged by this fix |

## File-Level Plan

| path or glob | action | notes |
|---|---|---|
| src/mes_dashboard/sql/query_tool/equipment_lots.sql | edit | IP-1: TRIM line 31; add `AND {{ CONTAINER_FILTER }}` after line 42; update header comment. Outer SELECT already projects `CONTAINERNAME` (line 56) — TRIM inside CTE suffices, no outer-SELECT change |
| src/mes_dashboard/services/query_tool_service.py | edit | IP-2 (`get_equipment_lots`, 2430-2500) + IP-4 (`execute_query_tool_job` lots branch, 2882-2894). Reuse `_build_two_filters` (2009-2023) pattern to avoid param-name collision on the single builder |
| src/mes_dashboard/routes/query_tool_routes.py | edit | IP-3: body parse ~674, async `_params` ~707-718, sync lots call ~747-753 |
| tests/test_query_tool_service.py | edit | IP-5: extend `TestGetEquipmentLots`; mock `read_sql_df_slow`, CHAR-padded/mixed-case `CONTAINERNAME` fixture; assert filter carried in `mock_load.call_args.kwargs`, not Python post-filter |
| tests/test_query_tool_routes.py | edit | IP-5: extend `TestEquipmentPeriodEndpoint`; per-kwarg `mock_lots.call_args.kwargs` assertion (non-default value); extend existing `test_equipment_lots_forwards_pagination` for omitted-field regression |
| tests/integration/test_query_tool_rq_async.py | edit | IP-5: new `TestEquipmentPeriodLotsParity` class (file currently only covers `status_hours`); include `inspect.signature(execute_query_tool_job).bind(**kwargs)` check; do not duplicate existing flag-on/off `status_hours` coverage |
| contracts/openapi.json | regenerate | IP-6: `cdd-kit openapi export --out contracts/openapi.json` (→ info.version 1.38.3) |
| contracts/api/openapi.json | regenerate | IP-6: `cdd-kit openapi export --out contracts/api/openapi.json` (→ info.version 1.38.3) |

## Contract Updates

- API: none to author — `contracts/api/api-contract.md` already at 1.38.3 (DONE). IP-6 only regenerates the two openapi.json mirrors to match.
- CSS/UI: none.
- Env: none.
- Data shape: none — TRIM changes the value only, not columns/row shape.
- Business logic: none — QT-05/QT-06 partial-trackout aggregation unchanged (read-only reference).
- CI/CD: none — all gates pre-existing (ci-gates.md).

## Test Execution Plan

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 (SQL TRIM correctness) | tests/test_query_tool_service.py::TestGetEquipmentLots::test_equipment_lots_containername_trimmed_char_padded | CHAR-padded CONTAINERNAME returned trimmed |
| AC-1 (sibling structural pin) | tests/test_query_tool_service.py::TestGetEquipmentLots::test_equipment_lots_sql_trims_containername_like_productlinename | SQL TRIMs CONTAINERNAME like PRODUCTLINENAME |
| AC-2 (non-empty rows) | tests/test_query_tool_service.py::TestGetEquipmentLots::test_equipment_lots_char_padded_fixture_returns_nonempty_rows | rows non-empty after trim |
| AC-4 (service filter semantics) | tests/test_query_tool_service.py::TestGetEquipmentLots::test_equipment_lots_container_names_filters_via_upper_trim_in | UPPER(TRIM(...)) IN filter applied |
| AC-4 (route forwarding) | tests/test_query_tool_routes.py::TestEquipmentPeriodEndpoint::test_equipment_lots_forwards_container_names_kwarg | `call_args.kwargs['container_names']` = non-default value |
| AC-5 (narrow before clamp) | tests/test_query_tool_service.py::TestGetEquipmentLots::test_equipment_lots_container_names_applied_in_sql_where_not_python_postfilter | filter in `mock_load.call_args.kwargs`, not Python post-filter |
| AC-6 (backward compat) | tests/test_query_tool_service.py::TestGetEquipmentLots::test_equipment_lots_omitted_container_names_unchanged_behavior | omitted field → identical behavior (1=1) |
| AC-6 (route omitted regression) | tests/test_query_tool_routes.py::TestEquipmentPeriodEndpoint::test_equipment_lots_forwards_pagination | existing test still green (extended) |
| Sync/async parity | tests/integration/test_query_tool_rq_async.py::TestEquipmentPeriodLotsParity::test_async_job_forwards_container_names_same_as_sync_route | async path forwards container_names same as sync |
| Sync/async worker bind | tests/integration/test_query_tool_rq_async.py::TestEquipmentPeriodLotsParity::test_execute_query_tool_job_lots_branch_binds_container_names_kwarg | `inspect.signature(...).bind(**kwargs)` succeeds |
| AC-3/AC-7 (frontend) | frontend/tests/query-tool/useLotEquipmentQuery.test.js | already DONE — 3 tests green |

Required phases (floor): collect, targeted, changed-area; plus contract (openapi/contract gate affected) and full for CI. Generate evidence with `cdd-kit test run`; the gate validates `test-evidence.yml`. Full ladder in test-plan.md §Test Execution Ladder / references/sdd-tdd-policy.md.

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- Do not edit `contracts/api/api-contract.md`, `contracts/CHANGELOG.md`, or the frontend composable/test — all DONE.
- `container_names` narrowing is `lots`-only; do not add it to other sub-types or the CSV export path.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.

## Known Risks

- **Param-name collision**: `get_equipment_lots` uses a single `QueryBuilder` for both `EQUIPMENT_FILTER` and the new `CONTAINER_FILTER`. Use the `_build_two_filters` (2009-2023) two-conditions-on-one-builder pattern (or add both conditions to the existing builder and index `builder.conditions[1]`) so both IN-lists share one param namespace — a naive second `QueryBuilder()` reuses `:in_0` and clobbers params.
- **openapi mirror gate**: `openapi-sync-gate` will FAIL until both `contracts/openapi.json` and `contracts/api/openapi.json` report `info.version: 1.38.3` (both currently 1.38.2). IP-6 is mandatory before gating (ci-gates.md blocking finding).
- **Full-suite sample regeneration**: a full pytest run regenerates the entire contract sample set; if that happens, `git checkout tests/contract/samples/` and re-stage only this change's samples (CLAUDE.md promoted learning).
- **CHAR-column consistency**: `_check_names_with_equipment`/`_build_two_filters` already treat CONTAINERNAME as CHAR — match their `UPPER(TRIM(...))`+strip convention exactly so the new filter and the equipment-resolution step agree.
- **Async parity is the core AC-4 gap**: the `lots` branch in `execute_query_tool_job` (2894) currently omits `container_names`; forgetting IP-4 leaves sync/async divergent and only fails at worker runtime — the `inspect.signature(...).bind()` test guards this.
