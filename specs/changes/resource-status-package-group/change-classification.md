# Change Classification

## Change Types
- primary: feature-add (api-behavior-change + ui-only-change)
- secondary: data-shape-change

## Risk Level
- medium

## Impact Radius
- cross-module (backend `resource_cache`/`resource_service`/`resource_routes` + frontend `resource-status` components)

## Tier
- 2

## Architecture Review Required
- no
- reason: No new module boundaries, no migration/rollback decision, no new Oracle tables, no new Redis keys. The cache strategy (in-process 46-row lookup dict, 7-day TTL independent of the 24h resource_cache cycle) is a bounded decision that fits inside `implementation-plan.md`; it does not warrant a separate `design.md`. The CHAR-type join-key consistency, NULL handling (91%), and TTL independence are constraints the planner can encode directly.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | Additive feature; current page behavior is unchanged for existing fields. |
| proposal.md | no | Single concrete request, no product investigation needed. |
| spec.md | no | No separate user-facing behavior decision beyond change-request. |
| design.md | no | Architecture Review not required. |
| qa-report.md | no | Routine pass/fail; use agent-log/qa-reviewer.yml pointer unless blocking findings emerge. |
| regression-report.md | no | Additive change; existing fields untouched. |
| visual-review-report.md | no | UI changes are additive; use agent-log/ui-ux-reviewer.yml pointer unless blocking. |
| monkey-test-report.md | no | Not a high-fuzz surface. |
| stress-soak-report.md | no | No new high-load path; lookup dict is 46 rows in-process. |

## Required Contracts
- API: yes — new `package_groups` query param on resource filter/status/summary/matrix endpoints; new `package_groups` array in filter-options response; new `PACKAGEGROUPNAME` field on status records. Update `contracts/api/api-contract.md` and `contracts/api/api-inventory.md`.
- CSS/UI: yes — new MultiSelect filter, EquipmentCard text row, MatrixSection expandable dimension. Update `contracts/css/css-contract.md` if new authored CSS is added (must be scoped under `.theme-resource-status`).
- Env: no
- Data shape: yes — new `PACKAGEGROUPNAME` field on merged resource record (nullable, NULL when PACKAGEGROUPID unset). Update `contracts/data/data-shape-contract.md`.
- Business logic: no — no new KPI/calculation; non-goal explicitly excludes OU%/AVAIL% package dimension.
- CI/CD: no — no new gate; existing backend/frontend/contract gates apply.

## Required Tests
- unit: yes — `resource_cache.py` lookup dict build + 7-day TTL independent refresh; CHAR join-key consistency; `get_merged_resource_status()` PACKAGEGROUPNAME NULL passthrough; `query_resource_filter_options()` returns `package_groups`; route per-kwarg forwarding assertion (non-default value). Frontend: FilterBar/EquipmentCard/MatrixSection component behaviour including NULL hide.
- contract: yes — API contract test for new param + response field; data-shape contract test for nullable `PACKAGEGROUPNAME`.
- integration: yes — confirm `package_groups` filter applies on both the warm-cache/snapshot path and any Oracle-fallback path in `resource_service.py`.
- E2E: no
- visual: yes — UI/UX review of EquipmentCard row, FilterBar, MatrixSection. Evidence via agent-log unless blocking.
- data-boundary: yes — 91% NULL PACKAGEGROUPID; frontend hides row on NULL; filter handles empty/NULL gracefully; CHAR-vs-string join key edge cases.
- resilience: no
- fuzz/monkey: no
- stress: no
- soak: no

## Required Agents
1. contract-reviewer — update API + data-shape contracts before implementation
2. test-strategist — author test-plan.md, map AC→tests
3. implementation-planner — produce implementation-plan.md after contracts + test-plan + ci-gates exist
4. backend-engineer — `resource_cache.py`, `resource_service.py`, `resource_routes.py` + backend tests (TDD)
5. frontend-engineer — `FilterBar.vue`, `EquipmentCard.vue`, `MatrixSection.vue`, `App.vue` + frontend tests
6. ci-cd-gatekeeper — write ci-gates.md
7. ui-ux-reviewer — review filter/card/matrix interaction and NULL semantics
8. qa-reviewer — release readiness decision (always last)

## Inferred Acceptance Criteria
- AC-1: A "Package Group" MultiSelect filter appears in the resource-status FilterBar; selecting one or more package groups narrows the equipment list and matrix to matching resources.
- AC-2: EquipmentCard displays `PACKAGEGROUPNAME` as a text row alongside workcenter/family when present; hides the row entirely when `PACKAGEGROUPNAME` is NULL (91% of resources).
- AC-3: MatrixSection supports Package as an expandable dimension without affecting existing OU%/AVAIL% KPI calculations (non-goal preserved).
- AC-4: `query_resource_filter_options()` returns a `package_groups` list; `resource_routes.py` reads the `package_groups` query param and forwards it to the service (asserted per-kwarg with a non-default value per CLAUDE.md route-forwarding discipline).
- AC-5: `get_merged_resource_status()` resolves `PACKAGEGROUPID`→`PACKAGEGROUPNAME` via the 46-row lookup dict; the CHAR-type join key is type-consistent so no rows are silently dropped or mismatched.
- AC-6: The lookup dict (`DW_MES_RESOURCE_PACKAGEGROUP`, 46 rows) loads in-process with a 7-day TTL that refreshes independently of the 24h `resource_cache` cycle; no new Redis key and no DB migration are introduced.
- AC-7: API and data-shape contracts document the new `package_groups` param and the nullable `PACKAGEGROUPNAME` field; contract tests pass.

## Tasks Not Applicable
- not-applicable: 1.3 (no design.md / architecture review), 2.3 (env contract), 2.5 (business logic contract), 2.6 (CI/CD contract), 3.3 (E2E/resilience), 3.4 (monkey tests), 3.5 (stress/soak), 4.3 (env/deploy), 5.2 (visual-reviewer — ui-ux-reviewer covers interaction/copy; no pixel-level visual blocking risk identified)

## Clarifications or Assumptions
- The `package_groups` filter applies on both the warm-cache/snapshot path and any Oracle-fallback path. Per CLAUDE.md Test Coverage Discipline, both paths must be tested for the new kwarg.
- No cross-filter narrowing between Package Group and other dimensions is stated. If resource-status filters cross-filter, add cross-filter narrowing tests; if intentionally non-cross-filtering, pin with a "does_not_narrow" test.
- New frontend CSS, if any, must be scoped under `.theme-resource-status` per Portal-Shell CSS Architecture Notes and pass `npm run css:check` Rule 6.
- This change modifies an existing page and does not add/remove a route; `data/page_status.json`, `asset_readiness_manifest.json`, and `route_scope_matrix.json` do not require edits.
