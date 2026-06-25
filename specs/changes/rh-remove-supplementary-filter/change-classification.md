# Change Classification

## Change Types
- primary: api-only-change, ui-only-change
- secondary: refactor (supplementary-filter removal), data-shape-change (query_id_input cache-key)

## Lane
- feature

## Risk Level
- medium

## Impact Radius
- module-level

## Tier
- 2

## Architecture Review Required
- no
- reason: Follows the already-established rh-primary-prefilter architectural pattern (BASE_WHERE prefilter + query_id_input cache-key isolation across sync/legacy-async/unified-job paths). No new module boundaries, no new data-flow, no migration/rollback decision. Predecessor change (ced4c83a + 5d9eeca3) set the precedent; this is the same shape applied to one more column with a UI-layer removal.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | Behavior delta is fully described in change-request and implementation-plan; no separate product investigation needed. |
| proposal.md | no | No user-facing product decision open; the four-column primary layout is already decided. |
| spec.md | no | No new spec surface; existing API/data contracts cover the param + cache-key change. |
| design.md | no | Architecture Review not required; follows established predecessor pattern. |
| qa-report.md | no | Routine pass/fail goes to agent-log/qa-reviewer.yml; promote only on blocking finding. |
| regression-report.md | no | Regression risk covered by required tests + reviewer log; promote only if regression found. |
| visual-review-report.md | no | UI change is panel removal + one MultiSelect column; agent-log/visual-reviewer.yml sufficient unless layout regression found. |
| monkey-test-report.md | no | Not a high-fuzz surface. |
| stress-soak-report.md | no | No new concurrency, queue, or cache-warmup introduced; query paths already exist. |

Artifact minimization rule: prefer `agent-log/*.yml` pointers for QA/visual/regression evidence; only promote to markdown on blocking findings or approved-with-risk.

## Required Contracts
- API: yes — POST reject-history query endpoints gain `reasons[]` and drop `workcenter_groups`; record in contracts/api/api-contract.md and regen both contracts/openapi.json and contracts/api/openapi.json.
- CSS/UI: yes — removal of .supplementary-panel/.supplementary-header/.supplementary-row/.supplementary-toolbar rules + .primary-prefilter-row grid change; verify contracts/css/css-inventory.md and css:check Rule 6.
- Env: no
- Data shape: yes — reasons[] added to query_id_input changes cache-key composition; verify contracts/data/data-shape-contract.md.
- Business logic: review — WHERE-semantics shift (DuckDB post-materialization → Oracle BASE_WHERE NVL/TRIM '(未填寫)' bucketing); confirm equivalence in contracts/business/business-rules.md.
- CI/CD: no

## Required Tests
- unit: yes — _build_base_where() emits reason_N bind params; route forwards reasons[] per-kwarg; workcenter_groups extraction removed; App.vue includes reasons[] in POST body; useRejectHistoryDuckDB no longer takes workcenterGroups
- contract: yes — reject-history API request-shape samples reflect reasons[] added / workcenter_groups removed; regen affected samples only
- integration: yes — reasons[] flows through legacy-async and unified-job paths; distinct reasons → distinct cache keys; mock is_async_available()=True
- E2E: yes — supplementary panel absent; 報廢原因 appears as 4th primary-prefilter column; Pareto cross-filter, pagination, CSV export work
- visual: yes — FilterPanel layout regression check (agent-log/visual-reviewer.yml unless blocking)
- data-boundary: yes — query_id_input cache-key boundary: (未填寫) bucket + empty-selection default must not collide with prior cache entries
- resilience: no
- fuzz/monkey: no
- stress: no
- soak: no

## Required Agents
- contract-reviewer
- test-strategist
- ci-cd-gatekeeper
- implementation-planner
- backend-engineer
- frontend-engineer
- ui-ux-reviewer
- visual-reviewer
- qa-reviewer

## Inferred Acceptance Criteria
- AC-1: The supplementary (second-layer) filter panel is fully removed from the reject-history UI (no supplementary-panel/supplementary-header/supplementary-row/supplementary-toolbar markup, props, emits, state, or CSS remain).
- AC-2: 報廢原因 (LOSSREASONNAME) appears as a 4th column in the primary-prefilter row alongside PJ Type, Package, and PJ Function, populated from GET /api/reject-history/options.
- AC-3: Selecting one or more 報廢原因 values applies the filter at the Oracle BASE_WHERE layer via NVL(TRIM(r.LOSSREASONNAME),'(未填寫)') IN (:reason_0, …) with reason_-prefixed binds, and narrows the returned dataset accordingly.
- AC-4: reasons[] is forwarded through all three query paths (sync, legacy async, unified async job) and is included in query_id_input so distinct reason selections produce distinct cache keys (no cross-selection cache bleed).
- AC-5: workcenter_groups is fully removed from request params, route extraction, and queryDetail/queryBatchPareto/getAvailableFilters; getAvailableFilters() is removed from useRejectHistoryDuckDB.ts.
- AC-6: Pareto cross-filter (paretoSelections), detail pagination, and CSV export continue to work unchanged against the retained DuckDB spool layer.
- AC-7: Result sets produced by the new BASE_WHERE 報廢原因 prefilter are equivalent to those previously produced by the supplementary DuckDB-layer reason filter for the same selection (including the (未填寫) bucket).
- AC-8: API request contract and OpenAPI exports (contracts/openapi.json + contracts/api/openapi.json) reflect reasons[] added / workcenter_groups removed, and css:check passes after the CSS removal + grid change.

## Tasks Not Applicable
- not-applicable: 1.3, 2.3, 2.6, 3.3, 3.4, 3.5, 4.3, 4.4

## Clarifications or Assumptions
- Assumption: GET /api/reject-history/options already returns reasons (via reason_filter_cache.get_reject_reasons()); no new endpoint needed.
- Assumption: business-rule equivalence (BASE_WHERE prefilter vs old DuckDB supplementary filter including (未填寫) bucketing) holds; flagged for explicit contract-reviewer confirmation.
- Assumption: no tier-floor-override needed — no inert concurrency-critical module or flag-gated wiring introduced; query paths already exist.
- Open: exact reject-history service/cache filenames are truncated in project-map (CER-001). Resolve before backend implementation.
