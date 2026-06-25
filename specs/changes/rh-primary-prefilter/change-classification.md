# Change Classification

## Change Types
- primary: feature-enhancement, api-only-change, ui-only-change
- secondary: business-logic-change (BASE_WHERE filter semantics, NVL/TRIM NULL handling)

## Risk Level
- medium

## Impact Radius
- module-level

(Touches reject-history backend + frontend. Reuses shared `container_filter_cache` and
production-history filter-options API in read/consume direction only — no modification
to shared producers.)

## Tier
- 2

## Architecture Review Required
- no
- reason: The key design decision (BASE_WHERE vs WHERE_CLAUSE injection layer) is already
  researched, confirmed, and fixed in the change request constraints. No new module boundary,
  no data-flow restructuring, no migration/rollback decision.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | Fully captured in change-request.md Known Context |
| proposal.md | no | Single confirmed approach; no option space |
| spec.md | no | Behavior fits in implementation-plan + AC |
| design.md | no | Architecture Review not required; task 1.3 skipped |
| qa-report.md | no | Routine pass/fail in agent-log/qa-reviewer.yml |
| regression-report.md | no | Promote to yes only if blocking regression found |
| visual-review-report.md | no | Additive UI; reviewer confirmation via agent-log sufficient |
| monkey-test-report.md | no | Not a high-load/sequence-fuzz surface |
| stress-soak-report.md | no | Change reduces Oracle load; no new load path added |

Artifact minimization:
- Prefer optional `agent-log/*.yml` pointers for routine review evidence.
- Create report markdown only for blocking findings, approved-with-risk, visual evidence bundles, or high-risk load/soak results.
- Later artifacts should reference earlier artifacts by path/section/id instead of duplicating full content.

## Required Contracts
- API: yes — `contracts/api/api-contract.md` (+ regenerate both `contracts/openapi.json`
  AND `contracts/api/openapi.json`). Three new optional request params (pj_types /
  packages / pj_functions) on primary query endpoint.
- CSS/UI: no — three MultiSelects reuse existing FilterPanel styling/tokens; additive only.
- Env: no — no new env var or runtime config.
- Data shape: yes — `contracts/data/data-shape-contract.md`. Request-side filter param
  shape and `(NA)` sentinel handling for nullable LEFT JOIN columns.
- Business logic: yes — `contracts/business/business-rules.md`. Prefilter semantics:
  empty selection = no restriction; NVL/TRIM NULL-container sentinel `(NA)`;
  PJ_BOP explicitly out of scope.
- CI/CD: no — no new gate, workflow, or retention change.

## Required Tests
- unit: yes — `_build_where_clause` / `_prepare_sql` per-kwarg assertions (new params
  render into BASE_WHERE not WHERE_CLAUSE); route forwarding per-kwarg with non-default values
- contract: yes — endpoint request/response sample regeneration; openapi parity for both
  openapi.json copies
- integration: yes — route-level: non-empty prefilter reaches service with BASE_WHERE
  populated; empty selection = current-behavior equivalence
- E2E: yes — extend `frontend/tests/playwright/reject-history-filter.spec.ts`
- visual: no
- data-boundary: yes — `(NA)` sentinel; NULL-container rows not dropped; malformed/absent
  params handled
- resilience: no
- fuzz/monkey: no
- stress: consider-only (change is load-reducing); no durable report required
- soak: no

## Required Agents
1. contract-reviewer
2. test-strategist
3. ci-cd-gatekeeper
4. implementation-planner
5. backend-engineer
6. frontend-engineer
7. ui-ux-reviewer
8. qa-reviewer

## Inferred Acceptance Criteria
- AC-1: Primary query endpoint accepts three new optional params (pj_types, packages,
  pj_functions); documented in API contract and both openapi.json exports.
- AC-2: Non-empty filter values are injected into `{{ BASE_WHERE }}` inside `reject_raw`
  CTE (NOT `{{ WHERE_CLAUSE }}`).
- AC-3: Conditions use `NVL(TRIM(c.PJ_TYPE/PRODUCTLINENAME/PJ_FUNCTION), '(NA)') IN (...)`
  form; NULL container values are not silently dropped; selecting `(NA)` returns
  NULL-container rows.
- AC-4: Empty selection for any filter produces no restriction — results equivalent to
  current behavior (backward compatible).
- AC-5: Three new MultiSelects render in FilterPanel primary section (same layer as date
  range); cross-filter options sourced from existing `container_filter_cache` /
  production-history filter-options API.
- AC-6: PJ_BOP is not added anywhere (no param, no SQL clause, no UI control).
- AC-7: Prefilters + supplementary (DuckDB) filters combine correctly end-to-end.

## Parity Risk
New BASE_WHERE params must flow identically through both sync and async/RQ routing and
into spool/cache keys. Implementation-planner must address this explicitly.

## Tasks Not Applicable
- not-applicable: 1.3, 2.2, 2.3, 2.6, 3.5, 4.3, 4.4, 5.2

## Clarifications or Assumptions
- Three new params are optional and additive (no removal/rename of existing fields),
  so the API change is non-breaking under `deprecate-2-minors` policy — minor schema bump.
- Production-history `/api/production-history/filter-options` endpoint is stable and
  intended for cross-page reuse; any required modification to that producer would
  force re-classification upward (cross-module).
- No Oracle index/schema work (stated non-goal).

## Context Manifest Draft

### Affected Surfaces
- reject-history backend (service + route + SQL)
- reject-history frontend (FilterPanel, App, filters core)
- shared cross-filter consumption (container_filter_cache, production-history
  filter-options API — read/consume only)

### Allowed Paths
- specs/changes/rh-primary-prefilter/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/services/reject_history_service.py
- src/mes_dashboard/routes/reject_history_routes.py
- src/mes_dashboard/sql/reject_history/
- src/mes_dashboard/services/container_filter_cache.py
- frontend/src/reject-history/
- frontend/src/core/reject-history-filters.ts
- frontend/src/shared-ui/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- tests/test_reject_history_service.py
- tests/test_reject_history_routes.py
- tests/test_reject_history_async_routes.py
- tests/test_reject_history_unified_job.py
- tests/contract/
- frontend/tests/playwright/reject-history-filter.spec.ts
- frontend/tests/validation/useRejectHistory.validation.test.js

### Agent Work Packets

#### change-classifier
- specs/changes/rh-primary-prefilter/
- specs/context/project-map.md
- specs/context/contracts-index.md

#### contract-reviewer
- specs/changes/rh-primary-prefilter/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md

#### test-strategist
- specs/changes/rh-primary-prefilter/
- tests/test_reject_history_service.py
- tests/test_reject_history_routes.py
- tests/test_reject_history_async_routes.py
- tests/contract/
- frontend/tests/playwright/reject-history-filter.spec.ts
- frontend/tests/validation/useRejectHistory.validation.test.js

#### ci-cd-gatekeeper
- specs/changes/rh-primary-prefilter/
- contracts/ci/ci-gate-contract.md

#### implementation-planner
- specs/changes/rh-primary-prefilter/
- specs/context/project-map.md
- specs/context/contracts-index.md

#### backend-engineer
- specs/changes/rh-primary-prefilter/
- src/mes_dashboard/services/reject_history_service.py
- src/mes_dashboard/routes/reject_history_routes.py
- src/mes_dashboard/sql/reject_history/
- src/mes_dashboard/services/container_filter_cache.py
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- tests/test_reject_history_service.py
- tests/test_reject_history_routes.py
- tests/test_reject_history_async_routes.py
- tests/test_reject_history_unified_job.py
- tests/contract/

#### frontend-engineer
- specs/changes/rh-primary-prefilter/
- frontend/src/reject-history/
- frontend/src/core/reject-history-filters.ts
- frontend/src/shared-ui/
- frontend/tests/playwright/reject-history-filter.spec.ts
- frontend/tests/validation/useRejectHistory.validation.test.js

#### ui-ux-reviewer
- specs/changes/rh-primary-prefilter/
- frontend/src/reject-history/
- frontend/src/shared-ui/

#### qa-reviewer
- specs/changes/rh-primary-prefilter/
- contracts/
