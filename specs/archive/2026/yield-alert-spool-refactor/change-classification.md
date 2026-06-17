# Change Classification

## Change Types
- primary: `refactor`, `business-logic-change`
- secondary: `api-only-change` (response shape: type selector param + new SOURCE_CODE/LOT column), `ui-only-change` (type selector UI + LOT column), `data-shape-change` (spool granularity + new dimension column)

## Risk Level
- high

## Impact Radius
- cross-module (backend spool/service/SQL/route + frontend DuckDB compute + shared filter orchestrator + spool infra)

## Tier
- 1

Rationale: The change rewrites the data-source path (ERP_WIP_MOVETXN → ERP_WIP_MOVETXN_DETAIL), unifies four views onto a single DuckDB spool, removes the live Oracle query path for trend/summary, multiplies spool row volume 2.4x (417,928 → 1,001,283 rows/month), and adds a new query dimension that crosses backend SQL, spool builder, route response contract, frontend DuckDB compute layer, and the shared filter orchestrator. This is system-adjacent (spool infra, namespace registration, RQ warmup worker) and carries non-obvious migration/rollback risk (parquet schema version bump). Tier 1.

## Architecture Review Required
- yes
- reason: This is a data-flow and module-boundary change (live-query → unified spool), a data-source migration (MOVETXN → MOVETXN_DETAIL), a breaking spool/parquet schema decision with rollback implications, and a compatibility trade-off (removing the live Oracle fallback path). spec-architect must record these decisions and the rollback/migration runbook in design.md before implementation-planner produces the execution packet.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | yes | Existing dual-source behavior (MOVETXN summary vs DETAIL alerts) and live-query path are being changed/removed; regression scope needs a documented baseline of current GA% totals and view-by-view data sources. |
| proposal.md | no | Technical decisions already settled in change-request; no separate product investigation needed. |
| spec.md | no | Behavior decisions fit in design.md + implementation-plan; no separate user-facing spec required. |
| design.md | yes | Architecture review required (data-flow/module-boundary/migration/rollback). Must precede implementation-planner. |
| qa-report.md | yes | High-risk correctness change (data-source swap, filter-semantics change); durable regression/correctness evidence needed for release sign-off. |
| regression-report.md | yes | Existing behavior changes (live-query removal, MOVETXN→DETAIL, filter removal); needs durable prose evidence that GA% totals and other reports are unchanged. |
| visual-review-report.md | yes | Four views (trend, Summary cards, heatmap, alert table) re-sourced to spool plus new type selector and LOT column — visual evidence bundle warranted. |
| monkey-test-report.md | no | Covered by routine e2e/abort tests; no durable prose evidence required. |
| stress-soak-report.md | yes | 2.4x spool volume + scheduled warmup interaction is a high-risk load decision; durable load/soak results needed. |

## Required Contracts
- API: yes — contracts/api/api-contract.md + contracts/api/openapi.json (regen): yield-alert query gains type param (GA%/GC%); alert-list response gains SOURCE_CODE/LOT field; trend/summary endpoints change source. contracts/api/api-inventory.md if endpoint set changes.
- CSS/UI: confirm-only — type selector + LOT column should reuse existing .theme-yield-alert scope (css-contract Rule 6). No contract change unless new component styling is introduced.
- Env: not-applicable — no new env var or secret.
- Data shape: yes — contracts/data/data-shape-contract.md: spool dataset gains type dimension + SOURCE_CODE/LOT + reject-linkage columns; parquet schema-version bump documented.
- Business logic: yes — contracts/business/business-rules.md: GC%/GA% scoping rule, PACKAGE IS NOT NULL removal rationale, SOURCE_CODE-NOT-NULL ⇒ scrap-only (TX=0) invariant, LOT dimension does not change yield granularity.
- CI/CD: confirm-only — parquet-rollback rm step and namespace-test gate vs existing contracts/ci/ci-gate-contract.md; no contract edit unless a new gate is added.

## Required Tests
- unit: yes — spool builder row-shape with SOURCE_CODE; GC%/GA% WIP_ENTITY_NAME split; reject-linkage merge; SOURCE_CODE-NOT-NULL ⇒ TX=0 invariant; frontend useYieldAlertDuckDB new-shape queries.
- contract: yes — API response shape (type param + LOT field) vs response-samples.json; data-shape contract conformance.
- integration: yes — mock-integration route → service → spool path; type param forwarding per-kwarg; both snapshot and Oracle-fallback paths.
- E2E: yes — tests/e2e/test_yield_alert_e2e.py: type switch GA%↔GC%, all four views from spool, LOT column visible in alert list.
- visual: yes — trend chart / Summary cards / heatmap / alert table after re-source; type-selector states.
- data-boundary: yes — DETAIL-table malformed/null SOURCE_CODE and PACKAGE rows; GC% wafer-sort PACKAGE=NA handling.
- resilience: yes — spool-warmup failure path (no live-query fallback now) → graceful degraded behavior; abort/in-flight.
- fuzz/monkey: no — existing route fuzz coverage sufficient.
- stress: yes — tests/stress/test_yield_alert_stress.py: 2.4x spool volume build + DuckDB browser query latency.
- soak: yes — scheduled rq_yield_alert_worker warmup with the larger spool over time (weekly soak lane).

## Required Agents
1. `contract-reviewer` — update/create contracts in contracts/ before implementation starts (API response shape, data-shape, business-rules).
2. `spec-architect` — author design.md (data-source decision, spool namespace/granularity, parquet schema-version + rollback runbook, reject-linkage merge, removal of live-query path).
3. `test-strategist` — write test-plan.md.
4. `ci-cd-gatekeeper` — write ci-gates.md.
5. `implementation-planner` — write implementation-plan.md after design + contracts + test plan + CI gates are known.
6. `backend-engineer` — spool builder, service orchestration, SQL (alerts.sql + SOURCE_CODE, trend/summary → spool-query-only or delete), namespace registration, reject-linkage merge, unit + integration tests.
7. `frontend-engineer` — type-selector UI, LOT column, useYieldAlertDuckDB.ts new spool shape, utils.ts, orchestrator type-param, frontend tests.
8. `stress-soak-engineer` — validate spool build + DuckDB query under 2.4x volume; soak with rq_yield_alert_worker warmup.
9. `ui-ux-reviewer` — type selector interaction + LOT column accessibility/copy.
10. `visual-reviewer` — trend chart, Summary cards, heatmap, alert table after the spool-unification; type-selector visual states.
11. `qa-reviewer` — release readiness, regression scope (correctness of GA%/GC% totals vs current production behavior).

## Inferred Acceptance Criteria
- AC-1: The primary (date-level) yield-alert query exposes a process-type selector (GA% packaging / GC% point-test); switching it scopes all four views to the matching WIP_ENTITY_NAME LIKE 'GA%' or 'GC%' lots.
- AC-2: All four views (yield trend, Summary cards, heatmap, alert list) are computed from a single DuckDB spool dataset; the live Oracle query path in trend.sql/summary.sql is no longer invoked at request time.
- AC-3: For GA%, total TRANSACTION_QTY and SCRAP_QTY computed from ERP_WIP_MOVETXN_DETAIL via the spool match the prior ERP_WIP_MOVETXN-based values within the verified equality (TX=70,494,377; SCRAP=81,972) — no yield regression.
- AC-4: The alert list shows a LOT dimension (SOURCE_CODE, e.g. GA26020192-A00-003-01); SOURCE_CODE NOT NULL rows (scrap-only, TX=0) do not inflate the TX numerator; work-order yield granularity is unchanged.
- AC-5: Reject linkage is produced from the single initial spool pull (no separate _compute_reject_linkage Oracle round-trip at request time).
- AC-6: The spool builder successfully produces and queries the ~1,001,283 rows/month dataset within stress thresholds; the parquet _SCHEMA_VERSION is bumped and the rollback runbook includes the rm cleanup step.
- AC-7: Removing the PACKAGE IS NOT NULL filter for GA% leaves GA% results unchanged (PACKAGE=NA count is 0 for GA%); GC% wafer-sort PACKAGE=NA lots are correctly retained.
- AC-8: Other reports (WIP, Hold, reject-history) and the shared useFilterOrchestrator consumers are unaffected (additive-only change to shared composable).

## Tasks Not Applicable
- not-applicable: 2.3 (env contract — no env var change), 4.3 (env/deploy — no deployment change)

## Clarifications or Assumptions
- Assumption: a new or re-shaped spool namespace is needed (current namespace is yield_alert_dataset); whether to reuse it with a schema-version bump or introduce a new namespace is a design.md decision (ADR-worthy, cf. ADR-0002/0005).
- Assumption: no new env var or secret; parquet _SCHEMA_VERSION is a code constant.
- Assumption: the type selector reuses the existing .theme-yield-alert CSS scope and existing shared components (MultiSelect/segmented control) additively — no new CSS token. Confirm with ui-ux-reviewer.
- Assumption: the already-done uncommitted edits (App.vue PageHeader removal, trend/summary unused-column removal) are part of this change's diff and must be covered by its tests.
- Open for design: whether removing the live Oracle trend/summary path leaves an acceptable degraded mode when spool warmup fails (resilience AC); spec-architect to decide fallback strategy.

## Context Manifest Draft
→ see specs/changes/yield-alert-spool-refactor/context-manifest.md (already updated)
