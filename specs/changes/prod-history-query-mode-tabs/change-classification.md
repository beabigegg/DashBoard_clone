# Change Classification

## Change Types
- primary: ui-redesign, business-logic-change
- secondary: api-change (payload contract), feature-enhancement

## Risk Level
- medium

## Impact Radius
- module-level

## Tier
- 2

## Architecture Review Required
- yes
- reason: The change makes `start_date`/`end_date` genuinely optional and introduces an all-time / wide-cap Oracle query path for identifier-mode queries. The change request flags a performance concern (CONTAINERNAME / MFGORDERNAME predicates must stay performant; the all-time path must not become an unbounded full-table scan). Whether to allow truly unbounded scans vs. impose a wide date cap is an architecture decision affecting Oracle load and must be reviewed before implementation. It is also a follow-up architecture fix to a shipped change, so mode-split validation semantics need a deliberate design decision.

## Required Artifacts
Always required: change-request.md, change-classification.md, test-plan.md, ci-gates.md, tasks.yml

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | yes | Existing single-panel behavior (mandatory TYPE + dates, validate_query_params hard-requires dates at ~line 99) is being changed; regression scope must be captured. |
| proposal.md | yes | Architecture Review Required = yes; the optional/wide-cap query-path decision and the two-tab interaction model need a recorded proposal for the architecture reviewer to sign off. |
| spec.md | no | Tier 2 module-level change; test-plan + proposal are sufficient. |
| design.md | no | Proposal covers the design decision; no separate cross-module design artifact needed at this tier. |
| qa-report.md | yes | UI redesign with explicit success criteria requiring functional verification; QA fixback loop needs a report. |
| regression-report.md | yes | Backward-compat constraint is explicit (existing callers that always send start_date/end_date must behave exactly as before); regression scope must be recorded. |

## Required Contracts
- API: `contracts/api/api-contract.md` — POST /api/production-history/query payload: `start_date`/`end_date` change from required to conditionally-optional (required in classification mode, optional in identifier mode). `contracts/api/api-inventory.md` only if endpoint metadata changes (likely not).
- CSS/UI: `contracts/css/css-contract.md` — new tab UI and 清除篩選 button must use existing design tokens; verify no new `@layer`. `contracts/css/css-inventory.md` only if a new authored CSS source file is added (none expected).
- Env: none
- Data shape: `contracts/data/data-shape-contract.md` — review only; result data shape unchanged. Confirm no row-shape impact from the all-time query path.
- Business logic: `contracts/business/business-rules.md` — new per-mode validation rule: identifier-mode queries permitted with no date bound; classification-mode queries still require TYPE + dates.
- CI/CD: none — no CI gate or pipeline change expected.

## Required Tests
- unit: backend `validate_query_params` per-mode logic; frontend `useProductionHistory` / `useFirstTierFilters` validation + broadened reset (清除篩選).
- contract: `test_api_contract.py` — query endpoint accepts payload with omitted dates when identifier tokens present; still rejects classification-mode payload missing dates.
- integration: backend route-level test — identifier-only request returns results without dates; classification-only request without dates returns the validation error.
- E2E: Playwright — Tab B paste LOT ID and query without TYPE/dates succeeds; Tab A query with empty TYPE/dates blocked with clear message; 清除篩選 returns page to initial empty state.
- visual: visual review of the two-tab layout, Tab B with no date row, 清除篩選 button placement.
- data-boundary: data-shape boundary check that the all-time / wide-cap query result rows match the existing contract shape.
- resilience: none required (no new failure surface).
- fuzz/monkey: none required.
- stress: consideration required — identifier-mode all-time query is an unbounded-scan risk; test-strategist to decide whether `tests/stress/test_production_history_stress.py` needs a no-date scenario.
- soak: none required.

## Required Agents
- spec-architect (Architecture Review Required = yes; reviews the optional-date / wide-cap query-path decision in proposal.md)
- backend-engineer
- frontend-engineer
- test-strategist
- contract-reviewer
- ui-ux-reviewer
- visual-reviewer
- ci-cd-gatekeeper
- qa-reviewer

## Inferred Acceptance Criteria
- AC-1: The Production History 查詢 page presents two explicit query-mode tabs — Tab A 「依產品分類查詢」 and Tab B 「依識別碼查詢」 — and the active tab is switchable by the user.
- AC-2: Tab A shows the four cached MultiSelect filters (TYPE/PACKAGE/BOP/FUNCTION) and the date range; submitting Tab A with empty TYPE or empty start/end dates is blocked with a clear validation message.
- AC-3: Tab B shows only the three wildcard textareas (工單號/LOT ID/Wafer LOT) with no date row and no required classification filters; a user can paste a LOT ID and query successfully without selecting TYPE or any date.
- AC-4: `production_history_service.validate_query_params` treats `start_date`/`end_date` as optional when identifier wildcard tokens (`mfg_orders`/`lot_ids`/`wafer_lots`) are present and no dates supplied — running a wide/all-time query — and still raises the dates-required error for classification-mode queries.
- AC-5: Identifier-mode no-date queries remain performant — the all-time path does not perform an unbounded full-table scan, or applies an agreed wide cap (decision recorded in proposal.md and verified).
- AC-6: A 「清除篩選」 button appears next to 查詢 and resets all first-tier selections, the three wildcard textareas, the date range (back to the default 30-day window), and any post-query supplementary/matrix filter, returning results to the empty state.
- AC-7: Existing callers that always send `start_date`/`end_date` (classification flow and existing tests) behave exactly as before — no regression in the cross-filter cache mechanism, wildcard grammar, second-tier filters, or matrix/detail rendering.
- AC-8: All new user-visible text (tab labels, 清除篩選, validation messages) is synchronized across all project locales.

## Tasks Not Applicable
- not-applicable: 2.3, 2.6, 4.3, 4.4

## Clarifications or Assumptions
- Assumption: the wide/all-time query for identifier mode reuses the existing `TRACKINTIMESTAMP`-chunked SQL path with the date predicate dropped (or widened to a cap); the exact mechanism is the subject of proposal.md and architecture review.
- Assumption: no new feature app, route, or endpoint is created — this modifies the existing `POST /api/production-history/query` and the existing `production-history` Vue app only.
- CER-001 (classifier's pending request for backend test filenames) — resolved by main Claude: `tests/test_production_history_service.py`, `tests/test_production_history_routes.py`, `tests/test_api_contract.py`, `tests/stress/test_production_history_stress.py` all confirmed to exist. No expansion needed.
- Atomic-split check: no trigger fired — single coherent feature, 3 contracts touched (< 5 threshold), one feature module. Proceeding as a single change.

## Context Manifest Draft

### Affected Surfaces
- Frontend: `frontend/src/production-history/` (App.vue, composables/, style.css)
- Backend: `src/mes_dashboard/services/production_history_service.py`, `src/mes_dashboard/services/production_history_sql_runtime.py`, `src/mes_dashboard/routes/production_history_routes.py`, `src/mes_dashboard/sql/production_history/`
- Contracts: api, business, css
- Tests: frontend validation + E2E, backend unit/contract/integration

### Allowed Paths
- specs/changes/prod-history-query-mode-tabs/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/production-history/
- src/mes_dashboard/services/production_history_service.py
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/routes/production_history_routes.py
- src/mes_dashboard/sql/production_history/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/business/business-rules.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/data/data-shape-contract.md
- tests/test_api_contract.py
- tests/test_production_history_service.py
- tests/test_production_history_routes.py
- tests/stress/test_production_history_stress.py
- frontend/tests/validation/
- frontend/tests/legacy/
- frontend/tests/abort/
- frontend/tests/playwright/

### Agent Work Packets

#### change-classifier
- specs/changes/prod-history-query-mode-tabs/
- specs/context/project-map.md
- specs/context/contracts-index.md

#### spec-architect
- specs/changes/prod-history-query-mode-tabs/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/services/production_history_service.py
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/sql/production_history/

#### backend-engineer
- specs/changes/prod-history-query-mode-tabs/
- src/mes_dashboard/services/production_history_service.py
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/routes/production_history_routes.py
- src/mes_dashboard/sql/production_history/
- tests/test_api_contract.py
- tests/test_production_history_service.py
- tests/test_production_history_routes.py
- tests/stress/test_production_history_stress.py
- contracts/api/api-contract.md
- contracts/business/business-rules.md

#### frontend-engineer
- specs/changes/prod-history-query-mode-tabs/
- frontend/src/production-history/
- frontend/tests/validation/
- frontend/tests/legacy/
- frontend/tests/abort/
- frontend/tests/playwright/
- contracts/css/css-contract.md
- contracts/css/css-inventory.md

#### test-strategist
- specs/changes/prod-history-query-mode-tabs/
- specs/context/project-map.md
- tests/
- frontend/tests/

#### contract-reviewer
- specs/changes/prod-history-query-mode-tabs/
- contracts/

#### ui-ux-reviewer
- specs/changes/prod-history-query-mode-tabs/
- frontend/src/production-history/
- contracts/css/

#### visual-reviewer
- specs/changes/prod-history-query-mode-tabs/
- frontend/src/production-history/
- contracts/css/

#### ci-cd-gatekeeper
- specs/changes/prod-history-query-mode-tabs/
- contracts/ci/

#### qa-reviewer
- specs/changes/prod-history-query-mode-tabs/
- contracts/
