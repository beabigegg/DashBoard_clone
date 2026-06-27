---
change-id: add-db-scheduling-page
schema-version: 0.1.0
last-changed: 2026-06-26
---

# Implementation Plan: add-db-scheduling-page

## Objective
Ship a read-only "DB生產排程助手" page under a new "生產輔助" drawer. Backend: a new
sync `GET /api/db-scheduling/queue` that, for every `D/B-START` lot, recommends running
DB-process equipment (primary WORKFLOWNAME match, BOP-first-char fallback), one row per
equipment, sorted per DB-04. All data derives from the existing `get_cached_wip_data()`
WIP cache (ADR 0013) — no new Oracle JOIN, no endpoint cache, no async path. Frontend: an
isolated Vue app rendering the queue table with a matchSource badge.

## Execution Scope

### In Scope
- New service `db_scheduling_service.get_db_scheduling_queue()` (cache-derived match/fallback/sort).
- New route blueprint `db_scheduling_bp` → `GET /api/db-scheduling/queue`.
- Blueprint registration in `routes/__init__.py` (NOT directly in app.py — see File-Level Plan).
- Regen of BOTH `contracts/api/openapi.json` AND `contracts/openapi.json`.
- New Vue app `frontend/src/db-scheduling/`, portal-shell registration (nav/registry/router).
- `data/page_status.json` + both `docs/migration/` manifests.
- Backend + navigation + CSS-scope unit tests, contract sample, Playwright E2E.

### Out of Scope (do not refactor / add)
- DW-station scheduling, manual equipment assignment, any MES/Oracle/Redis write (DB-05, AC-7).
- A dedicated Oracle `WITH start_lots … LEFT JOIN running_eqp` query, second cache layer, or RQ/async path (design.md rejected these).
- Touching `MultiSelect.vue` or other shared-ui except additively; no changes to existing endpoints/schemas.
- Emitting a placeholder row for `matchSource="none"` lots (zero rows; enum stays declared only).

## Required Changes
| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | tests (backend) | Write `tests/test_db_scheduling_service.py`, `tests/test_db_scheduling_routes.py`, `tests/test_db_scheduling_navigation.py`, `tests/test_db_scheduling_css_scope.py` per test-plan.md (failing first). | backend-engineer |
| IP-2 | service | Implement `services/db_scheduling_service.py::get_db_scheduling_queue()`. | backend-engineer |
| IP-3 | route | Implement `routes/db_scheduling_routes.py` (`db_scheduling_bp`, `GET /api/db-scheduling/queue`). | backend-engineer |
| IP-4 | wiring | Register `db_scheduling_bp` in `routes/__init__.py` (import + `register_blueprint` + `__all__`). | backend-engineer |
| IP-5 | contracts | Regen BOTH `contracts/api/openapi.json` AND `contracts/openapi.json`; extend `tests/contract/test_capture_samples.py` count by 1. | backend-engineer |
| IP-6 | frontend app | Create `frontend/src/db-scheduling/{App.vue,main.js,style.css}`; table + matchSource badge + refresh + loading/error/empty states; CSS scoped to `.theme-db-scheduling`. | frontend-engineer |
| IP-7 | portal nav | Add `production-assist` drawer (order 7) + DB排程助手 item in `navigationManifest.js`; register in `nativeModuleRegistry.js`; add `/db-scheduling` route in `router.js`. | frontend-engineer |
| IP-8 | nav status / migration | Add `db-scheduling` entry to `data/page_status.json` and to BOTH `docs/migration/asset_readiness_manifest.json` and `route_scope_matrix.json`. | frontend-engineer |
| IP-9 | E2E + checks | Write `frontend/tests/playwright/db-scheduling.spec.ts`; run `npm run type-check` and `npm run css:check`. | frontend-engineer |
| IP-10 | i18n | Add 生產輔助 / DB生產排程助手 + page-visible strings to ALL locale files (global rule 5). | frontend-engineer |

## Source Artifact Pointers
| source | relevant pointer | used for |
|---|---|---|
| design.md | Key Decisions (cache-source, Python fallback, none=0 rows, no Redis); Affected Components table | data-flow + file targets |
| business-rules.md | §DB Scheduling Rules DB-00 (12-SPEC list), DB-01..DB-05; Decision Table L296-300 | match/fallback/sort/read-only logic |
| data-shape-contract.md | §3.22 (11 columns, types, nullability, cardinality, null handling) | row shape + sort/NULLS-LAST |
| api-contract.md | endpoint row L253; §DbSchedulingQueueResponse L1053 | route response envelope + field types |
| test-plan.md | AC→test mapping table; Test Families; Test Update Contract | tests to write + sample-count update |
| ci-gates.md | Required Gates table (lint/build/unit/contract/e2e/data-boundary) | verification gates |
| change-classification.md | AC-1..AC-8; Required Contracts (regen BOTH openapi) | acceptance + contract regen scope |

## File-Level Plan
| path or glob | action | notes |
|---|---|---|
| src/mes_dashboard/services/db_scheduling_service.py | create | `get_db_scheduling_queue()`. Pattern after `qc_gate_service.py` (imports `get_cached_wip_data` from `core.cache`; reuse `_safe_value`/`_safe_int`/`_normalize_text` style helpers). DB-00 list as module constant pinned by membership test. Cache miss → `read_sql_df` fallback (or empty list), never 500. |
| src/mes_dashboard/routes/db_scheduling_routes.py | create | `db_scheduling_bp = Blueprint('db_scheduling', __name__, url_prefix='/api/db-scheduling')`; `@bp.route('/queue')` → `success_response(get_db_scheduling_queue())`. Auth = permission middleware (like `qc_gate_routes.py`, no decorator); 401 comes from middleware for unauthenticated. |
| src/mes_dashboard/routes/__init__.py | edit | Add import (L7-30 block), `register_blueprint(db_scheduling_bp)` (L35-57 block), and `'db_scheduling_bp'` in `__all__`. Do NOT register in app.py — design.md's "app.py ~904" is superseded by this actual registration pattern. |
| contracts/api/openapi.json, contracts/openapi.json | regen | `cdd-kit openapi export`; both files (CI `openapi-sync` checks the export). |
| tests/test_db_scheduling_service.py | create | Unit: AC-1..AC-5 rows in test-plan.md; cover U/E/P + unknown-prefix→none, NULLS-LAST sort, lot→many-equipment fan-out, cache-miss path. Mock at `db_scheduling_service.get_cached_wip_data`. |
| tests/test_db_scheduling_routes.py | create | 401 unauth, 200 + envelope, matchSource closed-enum. Sync endpoint, so no `is_async_available` mock needed; mock the service / cache. |
| tests/test_db_scheduling_navigation.py | create | Drawer order 7, link present, page_status entry. Reuse existing nav-contract helpers; do not duplicate drawer-validation logic. |
| tests/test_db_scheduling_css_scope.py | create | Assert feature CSS scoped under `.theme-db-scheduling` (css:check Rule 6). |
| tests/contract/test_capture_samples.py | edit | +1 sample count for new endpoint. |
| frontend/src/db-scheduling/{App.vue,main.js,style.css} | create | Isolated app; wrap in `.theme-db-scheduling`; table columns per §3.22; matchSource color-coded badge; refresh + loading/error/empty. |
| frontend/src/portal-shell/navigationManifest.js | edit | Add `{ id: 'production-assist', name: '生產輔助', order: 7, admin_only: false }` to `drawers`; add route entry `{ drawerId: 'production-assist', order: 1, displayName: 'DB生產排程助手' }`. ALSO update header comment "drawer orders MUST be distinct integers (1..6)" → 1..7. |
| frontend/src/portal-shell/nativeModuleRegistry.js | edit | Register `db-scheduling` mount gate (match existing native-app entries). |
| frontend/src/portal-shell/router.js | edit | Add `/db-scheduling` route. |
| data/page_status.json | edit | Add `db-scheduling` entry (manual; never auto-removed on revert). |
| docs/migration/asset_readiness_manifest.json, docs/migration/route_scope_matrix.json | edit | Add new page to BOTH (modernization policy). |
| frontend/tests/playwright/db-scheduling.spec.ts | create | Table render + empty state; LIFO route mocking (catch-all FIRST, `/api/db-scheduling/queue` LAST); pageRendered guard checks `.theme-db-scheduling`. |
| frontend i18n / locale files | edit | All locales for new visible strings. |

## Contract Updates
- API: schema/inventory/CHANGELOG already drafted (api-contract.md L253, L1053, L455). Only action: regen BOTH openapi.json files (IP-5).
- CSS/UI: new app scoped under `.theme-db-scheduling`; css-inventory entry already present. Run `npm run build` if source CSS changes (hashed dist).
- Env: none.
- Data shape: §3.22 already authored; implementation must match column names/types/nullability exactly.
- Business logic: DB-00..DB-05 authored; service is the implementation. Pin DB-00 12-SPEC list with a membership test.
- CI/CD: none.

## Test Execution Plan
| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 (all D/B-START lots; null BOP→empty) | tests/test_db_scheduling_service.py | start lots included; null-BOP lot emits 0 rows |
| AC-2 (workflow match) | tests/test_db_scheduling_service.py::test_workflow_match_sets_equipment_and_source | equipment set, matchSource="workflow" |
| AC-3 (BOP U/E/P + none) | tests/test_db_scheduling_service.py::test_bop_fallback_prefix_routing | correct group per prefix; unknown→none |
| AC-4 (sort NULLS LAST) | tests/test_db_scheduling_service.py::test_sort_order_nulls_last | PACKAGE_LEF→PJ_TYPE→WAFERLOT→UTS, nulls last |
| AC-6 (auth + envelope + enum) | tests/test_db_scheduling_routes.py | 401 unauth; 200 envelope; matchSource closed enum |
| AC-7 (drawer/link/page_status) | tests/test_db_scheduling_navigation.py | drawer order 7, link present, page_status entry |
| AC-8 (table render, empty, css scope) | frontend/tests/playwright/db-scheduling.spec.ts; tests/test_db_scheduling_css_scope.py | columns render; empty state; CSS scoped |
| AC-1..6 sample | tests/contract/test_capture_samples.py | sample count +1, sample captured |

Test phases (required floor — collect, targeted, changed-area; full ladder in test-plan.md):
run `cdd-kit test select add-db-scheduling-page` then `cdd-kit test run <phase>` for each.
The selector falls back to the `test file / command` column above only if test-plan.md's
mapping is absent. Implementation agents generate `test-evidence.yml`; the gate validates it.

## Handoff Constraints
- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.
- Backend lands first (IP-1..IP-5), then frontend (IP-6..IP-10).

## Known Risks
- EQUIPMENTS cardinality (design.md Open Risk): confirm at implementation whether `EQUIPMENTS` in the cached view is a single ID or delimited list. If delimited, split and emit one row per distinct value (DB-02 fan-out). Drives the §3.22 cardinality contract — decide before writing the fan-out test.
- DB-00 list duplicated in business-rules.md + service constant; pin with a membership test (design.md Open Risk).
- Cache-miss path: CI has no Redis → `get_cached_wip_data()` returns None. Service must degrade to `read_sql_df` or empty result, never 500 (design.md Open Risk); unit-test this branch explicitly.
- design.md says register the blueprint in app.py ~904; the actual codebase pattern registers via `routes/__init__.py::register_routes`. Plan follows the codebase pattern (IP-4); flagging the design/reality mismatch for awareness, not a blocker.
- navigationManifest.js header comment hard-codes "orders 1..6"; adding order 7 requires updating that comment, and any nav-contract test asserting the old upper bound must be updated.
