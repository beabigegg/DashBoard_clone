# Change Classification

## Change Types
- primary: data-model-change
- secondary: enhancement (data fidelity in production-history detail view)

## Risk Level
- medium

## Impact Radius
- module-level

## Tier
- 2

## Architecture Review Required
- no
- reason: Three-tier Oracle → spool → DuckDB architecture unchanged; only row-granularity within one report module shifts. Spool size impact is bounded and contained to production-history. No new dependency, no auth/payment/cross-module surface.

## Required Artifacts
Always required: change-request.md, change-classification.md, test-plan.md, ci-gates.md, tasks.yml

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | yes | Capture current MIN/MAX/SUM aggregation contract + DuckDB downstream consumers as baseline for diff review |
| proposal.md | no | change-request already contains target SQL and constraints; no alternatives to weigh |
| spec.md | no | Tier-2 data-shape change without new API surface; data-shape contract update suffices |
| design.md | no | Mechanical SQL rewrite + parity test rebase; no design questions after Resolved Decisions |
| qa-report.md | yes | Spool-size and DuckDB latency impact must be measured + reported; Matrix `COUNT(DISTINCT)` correctness must be verified against baseline |
| regression-report.md | no | qa-report.md covers regression evidence |

## Required Contracts
- API: no change — endpoint response envelope unchanged; detail rows still an array, only row semantics differ
- CSS/UI: no change
- Env: no change
- Data shape: **YES — update** `contracts/data/data-shape-contract.md`:
  1. row-granularity shift from "one row per (container, mfgorder, …, equipment) group" to "one row per LOTWIPHISTORY partial track-out"
  2. add `PJ_FUNCTION` column to detail spool schema (pre-staged for Change 3, NOT surfaced to filter UI in this change)
  3. document Matrix `count` semantics remain `COUNT(DISTINCT CONTAINERNAME)` over new row grain
- Business logic: **YES — update** `contracts/business/business-rules.md`: record TRACKIN_QTY / TRACKIN_TS / TRACKOUT_TS / TRACKOUT_QTY are now raw per-partial values; drop prior assumption "first partial = original batch quantity"
- CI/CD: no change (parity/safety/contract tests must be rebased but no new gate)

## Required Tests
- unit: backend `production_history_sql_runtime` (`compute_detail_page` / `compute_matrix_view` / `stream_export` / `_build_filter_where`) — row-count expectations updated; `PJ_FUNCTION` carried end-to-end; CSV export uses raw rows
- contract: data-shape contract test for production-history detail row schema (add `PJ_FUNCTION`; remove aggregated-column semantics); API response-envelope contract re-run
- integration: backend integration test with Oracle fixture asserting (a) detail row count = LOTWIPHISTORY row count for matched containers (not group count), (b) Matrix lot-count via DuckDB `COUNT(DISTINCT CONTAINERNAME)` matches prior aggregated baseline
- E2E: production-history page E2E — sample container with multiple partials renders multiple detail rows ordered by `TRACKIN_TS`
- visual: not applicable (Non-goals: no component structure change)
- data-boundary: detail row at month boundary — partial in month A vs month B for same container — attributed by `TRACKIN_TS`, no double-count in Matrix
- resilience: re-run `frontend/tests/abort/production-history-abort.test.js` — larger spool must not break cancellation
- fuzz/monkey: not applicable
- stress: re-run production-history stress test with new spool size; record p95 latency delta + parquet size delta in qa-report
- soak: not applicable

Parity fixtures:
- `tests/test_frontend_compute_parity.py` and `tests/test_frontend_duckdb_parity.py` production-history fixtures must be regenerated (new row shape)

## Required Agents
1. contract-reviewer — confirm + update data-shape + business-rules contracts BEFORE implementation
2. test-strategist — write test-plan.md (rebase parity/safety/contract fixtures; row-grain assertions)
3. backend-engineer — SQL rewrite, sql_runtime + service updates, spool schema + `PJ_FUNCTION` carry-through, CSV export
4. frontend-engineer — detail-table column order/format adjustments (if needed); ensure DuckDB consumer composables tolerate larger row count and continue Matrix via `COUNT(DISTINCT CONTAINERNAME)`
5. ci-cd-gatekeeper — write ci-gates.md
6. qa-reviewer — final release readiness, capture spool-size + p95 latency deltas in qa-report.md

## Inferred Acceptance Criteria
- AC-1: `production_history/main_query.sql` returns one row per LOTWIPHISTORY partial track-out (no `GROUP BY`); columns include `c.CONTAINERNAME, c.PJ_TYPE, c.PJ_BOP, c.PJ_FUNCTION, c.MFGORDERNAME, c.FIRSTNAME, c.PRODUCTLINENAME, h.WORKCENTERNAME, h.SPECNAME, h.EQUIPMENTID, h.EQUIPMENTNAME, h.TRACKINTIMESTAMP, h.TRACKOUTTIMESTAMP, h.TRACKINQTY, h.TRACKOUTQTY`
- AC-2: Detail spool parquet schema includes `PJ_FUNCTION` and aggregate-named columns are replaced by raw `TRACKINTIMESTAMP / TRACKOUTTIMESTAMP / TRACKINQTY / TRACKOUTQTY`
- AC-3: Matrix view `count` cell continues rendering lot-count via DuckDB `COUNT(DISTINCT CONTAINERNAME)`; for any (WC, Spec, Equipment × Month) cell equals lot-count produced by prior aggregated baseline against same Oracle fixture
- AC-4: Detail table UI shows one row per partial track-out, ordered by `TRACKIN_TS`; no "partial #" column (Resolved Decision 2)
- AC-5: CSV export emits raw per-partial rows with same column order as detail table; row count = API row count for same query
- AC-6: Existing production-history E2E, abort, contract, parity, safety tests pass after fixture rebase; no regression in non-production-history modules
- AC-7: qa-report.md records (a) spool parquet size delta vs baseline for a reference window, (b) p95 detail-page latency delta, (c) DuckDB query latency stays within existing budget — flag if any metric regresses beyond budget
- AC-8: `contracts/data/data-shape-contract.md` and `contracts/business/business-rules.md` reflect new row grain and dropped MAX/MIN/SUM assumptions before gate

## Tasks Not Applicable
- not-applicable: 2.1, 2.2, 2.3, 2.6, 3.4, 4.3, 4.4, 5.1, 5.2

(2.1 API / 2.2 CSS / 2.3 Env / 2.6 CI contracts unchanged; 3.4 monkey N/A; 4.3 env/deploy N/A; 4.4 CI workflows N/A; 5.1 UI/UX review N/A — Non-goals forbid component-structure change; 5.2 visual N/A)

## Clarifications or Assumptions
- Two open questions already closed in change-request "Resolved Decisions" block: (1) Matrix `count` stays `COUNT(DISTINCT CONTAINERNAME)`; (2) no "partial #" column — sort by `TRACKIN_TS`
- Assumption: `PJ_FUNCTION` is available on container source. Backend-engineer must verify before adding to projection; if missing, raise Context Expansion Request
- Assumption: production-history endpoint response envelope (success/error wrapper, pagination keys, sort allowlist) unchanged. API contract not bumped
- Assumption: Frontend production-history app is TypeScript (Change 1 merged), so per-app `.js` parity-test rename audit not required
- Assumption: Matrix aggregation already in DuckDB layer, so no backend matrix-aggregation logic needs addition — only the row source changes

## Context Manifest Draft

### Affected Surfaces
- Backend SQL: `src/mes_dashboard/sql/production_history/`
- Backend service runtime: `src/mes_dashboard/services/production_history_sql_runtime.py`
- Backend service / job: `src/mes_dashboard/services/production_history_service.py`, `production_history_job_service.py`
- Backend routes: `src/mes_dashboard/routes/production_history_routes.py` (response shape audit only)
- Frontend production-history app: `frontend/src/production-history/`
- Backend tests: production-history unit/integration/stress; parity fixtures
- Frontend tests: abort/legacy/validation
- Contracts: `contracts/data/data-shape-contract.md`, `contracts/business/business-rules.md`

### Allowed Paths
- specs/changes/prod-history-detail-raw-rows/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/data/
- contracts/business/
- contracts/api/
- contracts/ci/
- src/mes_dashboard/sql/production_history/
- src/mes_dashboard/sql/builder.py
- src/mes_dashboard/sql/filters.py
- src/mes_dashboard/sql/loader.py
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/services/production_history_service.py
- src/mes_dashboard/services/production_history_job_service.py
- src/mes_dashboard/routes/production_history_routes.py
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/core/spool_pipeline.py
- src/mes_dashboard/config/field_contracts.py
- shared/field_contracts.json
- frontend/src/production-history/
- frontend/src/core/field-contracts.ts
- frontend/src/core/endpoint-schemas.ts
- frontend/src/core/duckdb-client.ts
- frontend/src/core/types.ts
- frontend/tests/abort/production-history-abort.test.js
- frontend/tests/legacy/production-history.test.js
- frontend/tests/validation/useProductionHistory.validation.test.js
- tests/test_production_history_service.py
- tests/test_production_history_sql_runtime.py
- tests/test_production_history_routes.py
- tests/test_production_history_job_service.py
- tests/test_production_history_async_routes.py
- tests/test_frontend_compute_parity.py
- tests/test_frontend_duckdb_parity.py
- tests/fixtures/
- tests/e2e/test_production_history_e2e.py
- tests/stress/
- tests/integration/
- tests/conftest.py

### Agent Work Packets

#### contract-reviewer
- specs/changes/prod-history-detail-raw-rows/
- contracts/data/
- contracts/business/
- contracts/api/

#### test-strategist
- specs/changes/prod-history-detail-raw-rows/
- tests/
- frontend/tests/abort/
- frontend/tests/legacy/
- frontend/tests/validation/
- contracts/data/
- contracts/business/

#### backend-engineer
- specs/changes/prod-history-detail-raw-rows/
- src/mes_dashboard/sql/production_history/
- src/mes_dashboard/sql/builder.py
- src/mes_dashboard/sql/filters.py
- src/mes_dashboard/sql/loader.py
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/services/production_history_service.py
- src/mes_dashboard/services/production_history_job_service.py
- src/mes_dashboard/routes/production_history_routes.py
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/core/spool_pipeline.py
- src/mes_dashboard/config/field_contracts.py
- shared/field_contracts.json
- contracts/data/
- contracts/business/
- tests/

#### frontend-engineer
- specs/changes/prod-history-detail-raw-rows/
- frontend/src/production-history/
- frontend/src/core/field-contracts.ts
- frontend/src/core/endpoint-schemas.ts
- frontend/src/core/duckdb-client.ts
- frontend/src/core/types.ts
- shared/field_contracts.json
- contracts/data/
- frontend/tests/

#### ci-cd-gatekeeper
- specs/changes/prod-history-detail-raw-rows/
- .github/workflows/

#### qa-reviewer
- specs/changes/prod-history-detail-raw-rows/
- contracts/
