# Change Classification

## Change Types
- primary: feature-enhancement (filter-options expansion), business-logic-change (process_type LIKE-pattern set + query_id hash inputs)
- secondary: api-behavior-change (yield-alert query/view/cross-filter-options response contents + accepted process_type values), ui-only-change (process-type selector adds 4 options)

## Lane
- feature

## Risk Level
- medium

## Impact Radius
- module-level
  (yield-alert-center feature: yield_alert_routes / yield_alert_dataset_cache / yield_alert_sql_runtime + frontend App.vue. Cross-module note: `filter_cache.get_workcenter_groups()` / `_YIELD_WORKCENTER_GROUP_ORDER` / `_DEPT_SEQ_MAP` are shared; the change is explicitly scoped to leave the shared cache untouched and only re-point this page, which keeps blast radius module-level.)

## Tier
- 2

## Architecture Review Required
- no
  (Sub-change 2 is a data-flow source swap, but the design decision — drop the grouping/ordering layer for this page and return raw spool DEPARTMENT_NAME — is already resolved in change-request.md §Resolved Decisions, and it reuses the existing lines/packages/types/functions filter-options pattern verbatim rather than introducing a new pattern. No new module boundary, no migration/rollback trade-off. Implementation-planner captures the mechanics.)

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | Current GA/GC behavior and the two filter-option sourcing paths are already documented precisely in change-request.md §Known Context / §Constraints; no separate product investigation needed. |
| proposal.md | no | Behavior is user-specified and technically precise; no product decision to litigate. |
| spec.md | no | No new user-facing behavior decision beyond the resolved options; open question on the "其他(D%)" label is a copy tweak, not a spec. |
| design.md | no | No architecture review (reuses existing filter pattern; data-flow decision already resolved). |
| qa-report.md | yes (post-hoc) | qa-reviewer returned an approved-with-risk verdict (ready-with-known-risks: pre-existing Playwright CI-wiring gap + 3 unrelated pre-existing findings) — durable prose written per Artifact opt-in policy. |
| regression-report.md | no | Regression scope (existing GA/GC query_id stability, unchanged workcenter_groups for other pages) covered by tests + short agent-log pointer. Promote to yes only if a query_id-hash or shared-cache regression is found. |
| visual-review-report.md | no | Selector gains 4 text options only; visual evidence captured via agent-log/visual-reviewer.yml pointer unless a layout/overflow issue appears. |
| monkey-test-report.md | no | Not a high-fuzz surface. |
| stress-soak-report.md | no | No new concurrency/queue/cache wiring, no auto-refresh change; new options reuse the existing spool/query path. |

Artifact minimization:
- Prefer optional `agent-log/*.yml` pointers for routine review evidence.
- Create report markdown only for blocking findings, approved-with-risk, visual evidence bundles, or high-risk load/soak results.
- Later artifacts should reference earlier artifacts by path/section/id instead of duplicating full content.

## Required Contracts
- API: yes — `contracts/api/api-contract.md` (+ regenerate BOTH `contracts/openapi.json` AND `contracts/api/openapi.json`). Accepted `process_type` value set expands GA%/GC% → {GA%,GC%,GD%,F%,W%,D%}; `/api/yield-alert/view` and `/api/yield-alert/cross-filter-options` workcenter_groups source semantics change (now query_id-dependent raw DEPARTMENT_NAME). Update `contracts/api/api-inventory.md` only if a new endpoint appears (not expected).
- CSS/UI: no new authored CSS expected (selector adds text options within existing themed component). Confirm no unscoped rule; must stay scoped under yield-alert theme (css-contract Rule 6). No design-token change.
- Env: none — no env var, secret, or feature-flag added (change is not flag-gated).
- Data shape: yes — `contracts/data/data-shape-contract.md`. workcenter_groups option payload changes from grouped/ordered display names to raw spool DEPARTMENT_NAME distinct values; document the shape and that it now varies with query_id/process_type.
- Business logic: yes — `contracts/business/business-rules.md`. Record the process_type → WIP_ENTITY_NAME prefix LIKE-pattern mapping (GA%/GC%/GD%/F%/W%/D%), the prefix-mutual-exclusivity guarantee (esp. `F%` must not swallow GA/GC/other prefixes), and that GA remains a single option (non-goal: no WIP_CLASS_CODE sub-split).
- CI/CD: none — no gate/workflow change.

## Required Tests
- unit: yes — backend request validation accepts the 4 new process_type values and rejects unknown ones; query_id hash produces distinct ids per process_type (GA vs GC vs each new prefix); frontend process-type selector renders 6 options and its "clear query_id + force re-query" path fires for the new options (App.vue).
- contract: yes — yield-alert endpoint contract test for expanded accepted values + updated response sample capture for view/cross-filter-options; contract sample churn managed per CLAUDE.md (`git checkout tests/contract/samples/` then re-stage only yield-alert samples).
- integration: yes — cross-filter-options / view now derive workcenter_groups from the query_id spool via `SELECT DISTINCT DEPARTMENT_NAME`; assert workcenter_groups changes with process_type and no longer reads filter_cache/DW_MES_SPEC_WORKCENTER_V for this page. Per-kwarg assertions, both snapshot and Oracle-fallback paths, cross-filter "selecting A narrows B" for the new dimension source.
- E2E: yes — extend yield-alert-center Playwright/py E2E spec(s): select each new process_type option → query succeeds; station/workcenter filter reflects spool DEPARTMENT_NAME.
- visual: no — evidence via agent-log pointer only (text-only selector change); promote if overflow/wrapping appears.
- data-boundary: yes — assert behavior when spool has zero DEPARTMENT_NAME rows / null / whitespace (Oracle CHAR strip), and that new prefixes with no matching rows return an empty-but-valid result rather than error.
- resilience: no — no new failure surface beyond existing query path.
- fuzz/monkey: no.
- stress: no — reuses existing spool/query path; no new concurrency wiring.
- soak: no.

## Required Agents
- implementation-planner (required before any implementation agent; turns resolved decisions + contracts + tests into the execution packet)
- backend-engineer (request validation, query_id hash inputs, `_PRIMARY_DETAIL_SQL` LIKE patterns in yield_alert_dataset_cache, workcenter_groups source swap in yield_alert_sql_runtime / cross-filter-options)
- frontend-engineer (process-type selector 6 options, clear-query_id/force-requery wiring in App.vue, validation)
- test-strategist (acceptance-criteria → test mapping; unit/contract/integration/E2E/data-boundary coverage; enforce test-discipline rules)
- contract-reviewer (API + data-shape + business-rules changes; openapi export sync check)
- ui-ux-reviewer (new option labels/interaction correctness; resolves the "其他(D%)" naming open question)
- qa-reviewer (release readiness; confirms regression scope on existing GA/GC query_id stability and unchanged shared filter_cache)

(No spec-architect: Architecture Review = no.)

## Inferred Acceptance Criteria
- AC-1: The process-type selector renders exactly 6 options — existing GA%(量產) and GC%(點測) plus 重工(GD%), 委外(F%), WIP(W%), 其他(D%) — with final labels confirmed by ui-ux-reviewer (see open question on "其他(D%)").
- AC-2: Backend request validation accepts each of {GA%, GC%, GD%, F%, W%, D%} for process_type and rejects any other value with the standard error format.
- AC-3: Selecting a new process_type produces a distinct query_id and its own spool file (GA vs GC vs each new prefix hash to different ids), and the LIKE patterns are mutually exclusive — in particular `F%` does not match GA/GC/GD/D/W prefixes.
- AC-4: Switching to any new process_type triggers the existing "clear query_id + force re-query" flow and a successful `POST /api/yield-alert/query`.
- AC-5: `GET /api/yield-alert/view` and `GET /api/yield-alert/cross-filter-options` return workcenter_groups computed as `SELECT DISTINCT DEPARTMENT_NAME` from the query_id spool (raw values), no longer reading global filter_cache / DW_MES_SPEC_WORKCENTER_V for this page.
- AC-6: workcenter_groups options change with process_type / query_id, behaving identically to lines/packages/types/functions cross-filter dimensions (including cross-filter narrowing).
- AC-7: Rows previously invisible (WIP_ENTITY_NAME prefixes GD/F2/FA/FB/D2/W2) become queryable under the corresponding new option; a new option with zero matching rows returns a valid empty result, not an error.
- AC-8: The shared `filter_cache.get_workcenter_groups()` path and other pages that consume it are unchanged (no regression to non-yield-alert consumers).

## Tasks Not Applicable
- not-applicable: 1.3

## Clarifications or Assumptions
- Assumption: this is a `feature` lane, not `bug-fix` — the invisible ~1.65% of transactions is by-design filtering (only GA/GC exposed), not a defect.
- Assumption: no env flag gates this rollout (immediate behavior change).
- Open question carried from change-request: the "其他(D%)" label (D2 → WIP_CLASS_CODE PJ_NST_A) may be semantically inaccurate; ui-ux-reviewer to confirm final label and i18n sync across all languages (per user global i18n rule).
- Assumption: workcenter_groups return value becomes raw spool DEPARTMENT_NAME strings for this page (per §Resolved Decisions); data-shape-contract must record that the display grouping/ordering layer no longer applies here. If any downstream frontend chart (YieldStationChart.vue) depends on the old grouped names, that coupling must be surfaced by frontend-engineer.
- CER-001/CER-002 (module reads for yield_alert_dataset_cache.py / yield_alert_sql_runtime.py / yield_alert_routes.py / tests/) are pre-approved and folded directly into Allowed Paths below (see Context Manifest Draft), rather than left pending — they were the mechanical minimum needed for implementation-planner to scope edits and are already project-map-listed files.

## Context Manifest Draft

### Affected Surfaces
- yield-alert-center backend request handling & query hashing (routes)
- yield-alert-center dataset cache / Oracle detail SQL (process_type LIKE patterns, query_id hash)
- yield-alert-center filter-options / cross-filter-options SQL runtime (workcenter_groups source swap)
- yield-alert-center frontend page (process-type selector, force-requery, validation)
- API / data-shape / business-rules contracts for the yield-alert endpoints

### Allowed Paths
- specs/changes/yield-alert-filter-expansion/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/routes/yield_alert_routes.py
- src/mes_dashboard/services/yield_alert_dataset_cache.py
- src/mes_dashboard/services/yield_alert_sql_runtime.py
- src/mes_dashboard/services/filter_cache.py
- src/mes_dashboard/config/workcenter_groups.py
- src/mes_dashboard/sql/yield_alert/
- src/mes_dashboard/core/request_validation.py
- frontend/src/yield-alert-center/
- frontend/tests/validation/useYieldAlert.validation.test.js
- frontend/tests/yield-alert/
- frontend/tests/abort/yield-alert-abort.test.js
- frontend/tests/legacy/yield-alert-center-shell-contract.test.js
- frontend/tests/legacy/yield-alert-center-utils.test.js
- frontend/tests/playwright/yield-alert-center.spec.ts
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/css/css-contract.md
- tests/e2e/test_yield_alert_e2e.py
- tests/contract/samples/
- tests/contract/response-samples.json
- tests/contract/test_capture_samples.py
- tests/property/test_cross_filter.py
- tests/

(`filter_cache.py` and `config/workcenter_groups.py` are read-only to confirm the shared path is NOT modified — the change re-points the page away from them.)

### Agent Work Packets

#### change-classifier
- specs/changes/yield-alert-filter-expansion/
- specs/context/project-map.md
- specs/context/contracts-index.md

#### implementation-planner
- specs/changes/yield-alert-filter-expansion/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/routes/yield_alert_routes.py
- src/mes_dashboard/services/yield_alert_dataset_cache.py
- src/mes_dashboard/services/yield_alert_sql_runtime.py
- src/mes_dashboard/services/filter_cache.py
- src/mes_dashboard/config/workcenter_groups.py
- src/mes_dashboard/sql/yield_alert/
- frontend/src/yield-alert-center/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md

#### backend-engineer
- specs/changes/yield-alert-filter-expansion/
- src/mes_dashboard/routes/yield_alert_routes.py
- src/mes_dashboard/services/yield_alert_dataset_cache.py
- src/mes_dashboard/services/yield_alert_sql_runtime.py
- src/mes_dashboard/services/filter_cache.py
- src/mes_dashboard/config/workcenter_groups.py
- src/mes_dashboard/sql/yield_alert/
- src/mes_dashboard/core/request_validation.py
- tests/e2e/test_yield_alert_e2e.py
- tests/property/test_cross_filter.py
- tests/contract/samples/
- tests/contract/response-samples.json
- tests/contract/test_capture_samples.py
- tests/

#### frontend-engineer
- specs/changes/yield-alert-filter-expansion/
- frontend/src/yield-alert-center/
- frontend/tests/validation/useYieldAlert.validation.test.js
- frontend/tests/yield-alert/
- frontend/tests/abort/yield-alert-abort.test.js
- frontend/tests/legacy/yield-alert-center-shell-contract.test.js
- frontend/tests/legacy/yield-alert-center-utils.test.js
- frontend/tests/playwright/yield-alert-center.spec.ts

#### test-strategist
- specs/changes/yield-alert-filter-expansion/
- frontend/tests/validation/useYieldAlert.validation.test.js
- frontend/tests/yield-alert/
- frontend/tests/playwright/yield-alert-center.spec.ts
- tests/e2e/test_yield_alert_e2e.py
- tests/property/test_cross_filter.py
- tests/contract/samples/
- tests/contract/test_capture_samples.py

#### contract-reviewer
- specs/changes/yield-alert-filter-expansion/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md

#### ui-ux-reviewer
- specs/changes/yield-alert-filter-expansion/
- frontend/src/yield-alert-center/
- contracts/css/css-contract.md

#### qa-reviewer
- specs/changes/yield-alert-filter-expansion/
- src/mes_dashboard/routes/yield_alert_routes.py
- src/mes_dashboard/services/yield_alert_dataset_cache.py
- src/mes_dashboard/services/yield_alert_sql_runtime.py
- frontend/src/yield-alert-center/

### Context Expansion Requests
-

### Approved Expansions
- CER-001: src/mes_dashboard/services/yield_alert_dataset_cache.py, src/mes_dashboard/services/yield_alert_sql_runtime.py, src/mes_dashboard/routes/yield_alert_routes.py — folded into Allowed Paths above.
- CER-002: tests/ — folded into Allowed Paths above (backend unit-test file location for yield-alert request validation / query_id hashing to be confirmed by implementation-planner).
