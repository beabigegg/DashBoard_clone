# Change Classification

## Change Types
- primary: feature-add (api-only-change + ui-only-change)
- secondary: business-logic-change

## Lane
- feature

## Risk Level
- medium

## Impact Radius
- module-level

## Tier
- 2

## Architecture Review Required
- yes
- reason: Recommendation engine encodes non-trivial domain logic: (1) WORKFLOWNAME primary match vs BOP-first-char fallback dispatch, (2) BOP→equipment-group mapping (U/E/P), (3) multi-key sort and one-lot-to-many-equipment cardinality. Requires recorded design decision on cache-vs-Oracle data-flow before implementation.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | New page; no existing behavior. |
| proposal.md | no | Business rules settled in change-request.md. |
| spec.md | no | design.md + ACs cover behavior. |
| design.md | yes | Architecture Review Required = yes; matching/fallback/sort engine + cache-vs-Oracle decision needed before implementation-planner runs. |
| qa-report.md | no | Promote only on blocking finding. |
| regression-report.md | no | New isolated module. |
| visual-review-report.md | no | Promote only on blocking finding. |
| monkey-test-report.md | no | Read-only single-endpoint page. |
| stress-soak-report.md | no | ~689 lots, single read-only cache-backed endpoint. |

## Required Contracts
- API: contracts/api/api-contract.md, contracts/api/api-inventory.md; regen BOTH contracts/openapi.json AND contracts/api/openapi.json
- CSS/UI: contracts/css/css-inventory.md; new app scoped under .theme-db-scheduling
- Data shape: contracts/data/data-shape-contract.md
- Business logic: contracts/business/business-rules.md
- Env: no
- CI/CD: no

## Required Tests
- unit: yes — primary WORKFLOWNAME match, BOP-fallback U/E/P branches, sort precedence, lot→many-equipment expansion, STATUS='ACTIVE' filter, empty/no-match handling
- contract: yes — GET /api/db-scheduling/queue response schema + sample capture
- integration: yes — route forwarding, correct success_response wrapper key, STATUS='ACTIVE' filter in query
- E2E: yes — drawer 生產輔助 appears, /db-scheduling loads, table renders
- data-boundary: yes — null BOP, missing EQUIPMENTS, BOP outside U/E/P, missing sort-key columns
- resilience: no
- fuzz/monkey: no
- stress: no
- soak: no

## Required Agents
1. contract-reviewer — update API + data-shape + business + CSS contracts
2. test-strategist — write test-plan.md
3. spec-architect — write design.md
4. ci-cd-gatekeeper — write ci-gates.md
5. implementation-planner — write implementation-plan.md
6. backend-engineer — new route + service
7. frontend-engineer — new Vue app + portal-shell drawer
8. ui-ux-reviewer — drawer placement, navigation, i18n
9. visual-reviewer — page visual confirmation
10. qa-reviewer — release readiness

## Inferred Acceptance Criteria
- AC-1: New drawer 生產輔助 appears in portal-shell at order 7, containing DB生產排程助手 at /db-scheduling.
- AC-2: GET /api/db-scheduling/queue returns all D/B-START lots with recommended equipment list in standard success_response envelope.
- AC-3: Primary match uses WORKFLOWNAME against DB-process SPEC lots with STATUS='ACTIVE' and non-null EQUIPMENTS.
- AC-4: BOP fallback applies when no WORKFLOWNAME match: U→Eutectic/1DB/2DB group, E→Epoxy D/B, P→Solder/DBCB/錫膏網印; BOP outside U/E/P yields no-recommendation, not error.
- AC-5: Results sorted by PACKAGE_LEF → PJ_TYPE → WAFERLOT → UTS.
- AC-6: One lot mapping to multiple equipment is fully expanded; each row indicates primary-match vs fallback source.
- AC-7: Endpoint is GET-only; no writes to Oracle, MES, or any store.
- AC-8: Null BOP, missing EQUIPMENTS, missing sort-key columns handled without crash or 500.

## Tasks Not Applicable
- not-applicable: 2.3 (no env var), 2.6 (no CI/CD contract change), 3.5 (no stress/soak), 4.3 (no env/deploy change), 4.4 (no new CI workflow)

## Clarifications or Assumptions
- Data source is existing DWH.DW_MES_LOT_V (5-min WIP cache); no new Oracle-direct path unless design.md changes this.
- BOP fallback equipment groups and 12-entry DB-process SPEC list in change-request.md are authoritative for business-rules contract.
- MultiSelect.vue / shared-ui changes (if any) must be additive only.
- New user-visible text must be added to all i18n locales (global rule 5).
- Page registration touches navigationManifest.js, router.js, data/page_status.json, route_scope_matrix.json, asset_readiness_manifest.json per modernization policy.
