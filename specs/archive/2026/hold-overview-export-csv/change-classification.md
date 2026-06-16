# Change Classification

## Change Types
- primary: feature-add, ui-only-change, api-only-change
- secondary: data-export-change

## Lane
- feature

## Risk Level
- medium

## Impact Radius
- module-level

## Tier
- 3

## Architecture Review Required
- no
- reason: The change follows two established, proven patterns already in the codebase: frontend CSV assembly (`hold-history/App.vue` `_buildCsv()`/`_downloadCsv()`) and full-data/export parameter handling on an existing endpoint. There is no new module boundary, no new data flow, and no migration/rollback decision. The only non-trivial decision — how "full data" is fetched (remove pagination limit vs. `export=true` parameter) — is a localized implementation-plan choice, not an architecture decision. Task 1.3 (design review) is therefore not applicable.

## Required Artifacts

Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)

| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | Current paginated behavior is simple and fully captured in the change-request + implementation-plan; no separate product investigation needed. |
| proposal.md | no | Scope and pattern are already decided (mirror hold-history); no user-facing behavior decision to resolve. |
| spec.md | no | No new contract surface or behavior spec beyond the api-contract entry. |
| design.md | no | No architecture review required. |
| qa-report.md | no | Routine pass/fail evidence fits in `agent-log/qa-reviewer.yml`; no blocking-findings prose expected. |
| regression-report.md | no | Existing paginated query path is preserved (export is additive); regression scope is narrow and logged via agent-log. |
| visual-review-report.md | no | Button reuses existing `ui-btn ui-btn--secondary` style; visual confirmation fits in agent-log. |
| monkey-test-report.md | no | Not a high-churn interaction surface. |
| stress-soak-report.md | no | Full-data fetch risk is bounded by a row cap; no durable soak report needed. |

## Required Contracts
- API: `contracts/api/api-contract.md` — `/api/hold-overview/lots` gains a full-data/export mode (request param + unbounded/raised-limit response behavior). Update `contracts/api/api-inventory.md` and regenerate `contracts/openapi.json` if the request/response schema changes. CHANGELOG entry required.
- CSS/UI: `contracts/css/css-contract.md` / `contracts/css/css-inventory.md` — only if a new authored CSS source rule is added. Preferred: reuse existing `ui-btn` tokens (no contract change). Confirm during implementation.
- Env: none
- Data shape: `contracts/data/data-shape-contract.md` — the CSV export column set and the full-data row boundary (max rows returned in export mode) should be pinned here.
- Business logic: none
- CI/CD: none

## Required Tests
- unit: Frontend `_buildCsv()` / `_downloadCsv()` for hold-overview (correct columns, header order, BOM prefix, value escaping for commas/quotes/newlines, empty-result handling). Backend route unit test for the export/full-data parameter.
- contract: `/api/hold-overview/lots` export-mode request/response shape against `contracts/api/api-contract.md` (sample under `tests/contract/samples/`).
- integration: Route forwarding of the export/full-data flag through to the service (per-kwarg assertion per test-discipline rules), both snapshot and Oracle-fallback paths if both apply.
- E2E: `frontend/tests/playwright/hold-overview.spec.js` — click Export CSV, assert download is triggered and the request hits the full-data endpoint mode.
- visual: none (reuses existing button tokens; visual-reviewer confirms via agent-log).
- data-boundary: Export column set against `data-shape-contract.md`; malformed/missing-field rows in Lot data must not break CSV assembly.
- resilience: none required; optionally assert graceful UI handling if the full-data request fails.
- fuzz/monkey: none
- stress: Consideration only — full-data fetch removes the pagination cap; pin a maximum row count and add a bounded large-result test OR enforce a hard server-side row limit.
- soak: none

## Required Agents
- contract-reviewer
- test-strategist
- implementation-planner
- backend-engineer
- frontend-engineer
- ui-ux-reviewer
- visual-reviewer
- qa-reviewer

## Inferred Acceptance Criteria
- AC-1: An "Export CSV" button appears in the Hold Lot Details table/card header on the hold-overview page, using the same style (`ui-btn ui-btn--secondary`) and behavior as the hold-history DetailTable export button.
- AC-2: Clicking the button fetches the full Lot Details dataset (pagination limit removed/bypassed) rather than only the current page.
- AC-3: The downloaded CSV contains all current Hold Lot Details columns (lotId, workorder, qty, product, package, workcenter, holdReason, spec, age, holdBy, dept, holdComment, futureHoldComment) with a header row, in the displayed column order.
- AC-4: The CSV is produced client-side as a Blob download with a UTF-8 BOM prefix so Excel renders non-ASCII (Chinese) text correctly, matching the hold-history pattern.
- AC-5: Values containing commas, quotes, or newlines are correctly escaped, and missing/malformed field values do not break CSV generation.
- AC-6: The existing paginated `/api/hold-overview/lots` query behavior is unchanged for normal table rendering (export is additive).
- AC-7: The full-data/export request is bounded by an enforced maximum row count (or documented limit) so an unbounded fetch cannot exhaust server/browser resources.
- AC-8: While the export request is in flight, the button shows a loading state and is disabled to prevent duplicate concurrent exports.

## Tasks Not Applicable
- not-applicable: 1.3

## Clarifications or Assumptions
- Assumption: The export will reuse the existing `/api/hold-overview/lots` endpoint with a full-data/export mode rather than introducing a new endpoint.
- Assumption: CSV is assembled client-side (mirroring `hold-history`), not server-side via `core/post-export.ts`.
- Open question: What is the maximum acceptable Lot row count for a single export? A concrete cap is required to close AC-7. Default to the same cap hold-history uses if one exists.
- Assumption: If hold-overview supports multiple languages, all i18n files must be updated together per global i18n rule.

## Context Manifest Draft

### Affected Surfaces
- hold-overview report page (frontend Vue app + backend route/service)
- `/api/hold-overview/lots` API endpoint (export / full-data mode)
- CSV data-export boundary

### Allowed Paths
- specs/changes/hold-overview-export-csv/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/hold-overview/
- frontend/src/hold-history/
- frontend/src/core/post-export.ts
- frontend/src/core/
- frontend/src/query-tool/components/
- frontend/src/shared-ui/
- frontend/tests/playwright/hold-overview.spec.js
- frontend/tests/components/
- frontend/tests/validation/useHoldOverview.validation.test.js
- src/mes_dashboard/routes/hold_overview_routes.py
- src/mes_dashboard/services/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/data/data-shape-contract.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/CHANGELOG.md
- tests/contract/samples/
- tests/stress/

### Required Contracts
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/data/data-shape-contract.md
- contracts/css/css-contract.md (conditional — only if new authored CSS)

### Required Tests
- frontend/tests/playwright/hold-overview.spec.js
- frontend/tests/components/
- frontend/tests/validation/useHoldOverview.validation.test.js
- tests/contract/samples/
- tests/stress/ (bounded large-result test, conditional)

### Agent Work Packets

#### change-classifier
- specs/changes/hold-overview-export-csv/
- specs/context/project-map.md
- specs/context/contracts-index.md

#### implementation-planner
- specs/changes/hold-overview-export-csv/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md

#### backend-engineer
- specs/changes/hold-overview-export-csv/
- src/mes_dashboard/routes/hold_overview_routes.py
- src/mes_dashboard/services/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/data/data-shape-contract.md
- tests/contract/samples/
- tests/stress/

#### frontend-engineer
- specs/changes/hold-overview-export-csv/
- frontend/src/hold-overview/
- frontend/src/hold-history/
- frontend/src/core/post-export.ts
- frontend/src/core/
- frontend/src/query-tool/components/
- frontend/src/shared-ui/
- frontend/tests/playwright/hold-overview.spec.js
- frontend/tests/components/
- frontend/tests/validation/useHoldOverview.validation.test.js
- contracts/css/css-contract.md
- contracts/css/css-inventory.md

#### contract-reviewer
- specs/changes/hold-overview-export-csv/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/data/data-shape-contract.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/CHANGELOG.md

#### test-strategist
- specs/changes/hold-overview-export-csv/
- frontend/tests/
- tests/contract/samples/
- tests/stress/

#### ui-ux-reviewer
- specs/changes/hold-overview-export-csv/
- frontend/src/hold-overview/
- frontend/src/hold-history/
- contracts/css/css-contract.md

#### visual-reviewer
- specs/changes/hold-overview-export-csv/
- frontend/src/hold-overview/
- frontend/src/hold-history/

#### qa-reviewer
- specs/changes/hold-overview-export-csv/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md

### Context Expansion Requests
- request-id: CER-001
  requested_paths:
    - frontend/src/hold-overview/components/
    - frontend/src/hold-history/components/
  reason: The project-map truncates these component directories at max depth, so the exact DetailTable / card-header component files that host the table and the export button are not enumerable from the index. Implementation needs the precise component file paths to place the button and reuse the hold-history CSV helpers.
  status: pending
