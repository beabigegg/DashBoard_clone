# Change Classification

## Change Types
- primary: feature-enhancement, performance
- secondary: refactor (client-side caching logic in existing composables)

## Lane
- feature

<!-- Bug-fix sections intentionally omitted: existing behavior is correct, only inefficient. No data-correctness defect, no unknown root cause. This is a symptom-free performance/UX enhancement, not a symptom-driven bug fix. -->

## Risk Level
- low

## Impact Radius
- module-level (query-tool feature module only; no cross-module or backend surface)

## Tier
- 3

Rationale: low risk + module-level → Tier 3-4. Classified upward to Tier 3 (not 4) because there is a genuine data-freshness correctness risk: incorrect cache invalidation on filter change would surface stale results. The change is otherwise reversible and tightly scoped to 2-3 files plus their existing tests.

## Architecture Review Required
- no

No module-boundary change, no data-flow redesign, no migration/rollback decision. The work reuses existing `queried.lots`/`queried.jobs`/`queried.rejects` flags and existing call sites; it is a localized guard-and-invalidate pattern, not a new design.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | Current behavior is fully captured in change-request.md Original Request; no separate investigation needed. |
| proposal.md | no | No product/user-facing decision to arbitrate; approach is deterministic. |
| spec.md | no | No new behavior surface; success criteria fit in classification + implementation-plan. |
| design.md | no | No architecture review required. |
| qa-report.md | no | Routine pass/fail belongs in agent-log/qa-reviewer.yml unless a blocking finding arises. |
| regression-report.md | no | No existing-contract behavior change; regression risk covered by unit tests + agent log. |
| visual-review-report.md | no | No visual/CSS/layout output change — cached data is identical to freshly queried data. |
| monkey-test-report.md | no | Not a fuzz/robustness surface. |
| stress-soak-report.md | no | Client-side cache reduces load; no new high-load/long-running server path introduced. |

Artifact minimization: reviewers should record pass/fail and cache-invalidation evidence in agent-log/*.yml pointers, not standalone markdown.

## Required Contracts
- API: none (no endpoint, request/response, or async-routing change — queries reuse existing routes)
- CSS/UI: none (no visual output change)
- Env: none
- Data shape: none (cached payloads are the existing response shapes, unchanged)
- Business logic: none
- CI/CD: none

## Required Tests
- unit: cache-hit path skips re-query on same-filter sub-tab revisit; each of the 3 sub-tabs queries once per filter set; filter change (equipment/lot/workcenter-group/date-range) invalidates all sub-tab caches; explicit refresh re-queries; useLotDetail.ts parity behavior
- contract: n/a
- integration: n/a
- E2E: optional strengthening only (not required) — no duplicate HTTP/RQ job on tab revisit, assertable at Playwright level but unit-level call-count assertions are primary/lower-cost coverage
- visual: n/a
- data-boundary: n/a
- resilience: n/a
- fuzz/monkey: n/a
- stress: n/a
- soak: n/a

## Required Agents
- implementation-planner — turns the caching/invalidation decisions and success criteria into the execution packet before frontend work starts
- frontend-engineer — implements cache-aware setActiveSubTab()/queryActiveSubTab() guards and filter-change invalidation in the three composables
- test-strategist — designs/extends the unit tests (call-count assertions on cache-hit vs invalidation) and maps them to acceptance criteria
- qa-reviewer — release-readiness confirmation, focused on the stale-data-after-filter-change risk

Not required and why: contract-reviewer (no contract touched — qa-reviewer confirms the zero-contract claim holds), ui-ux-reviewer/visual-reviewer (no visual output change), spec-architect (no architecture review), stress-soak-engineer/e2e-resilience-engineer (no new load surface).

## Inferred Acceptance Criteria
- AC-1: Revisiting a sub-tab (生產紀錄/維修紀錄/報廢紀錄) that was already queried under the current filter set issues no new HTTP request or RQ job — the cached result is reused.
- AC-2: Under one unchanged filter set, each of the three sub-tabs queries Oracle exactly once (on first entry), verified by query-function call counts.
- AC-3: Changing any filter axis (equipment_ids, container_ids/lot list, workcenter_groups, or date range) invalidates the cached results for all sub-tabs.
- AC-4: After a filter change, the next entry into any sub-tab re-queries and never displays stale (pre-change) data.
- AC-5: An explicit user refresh re-queries the active sub-tab even when filters are unchanged.
- AC-6: useLotDetail.ts is audited for the same setActiveSubTab re-query gap; if present it is fixed consistently, if absent that is recorded (no silent scope drop).
- AC-7: The queried.lots/queried.jobs/queried.rejects flags are the source of truth for the cache-hit decision and are reset in lockstep with cache invalidation.

## Tasks Not Applicable
- not-applicable: 1.3, 2.2, 2.3, 2.4, 2.5, 2.6, 3.3, 3.5, 4.1, 4.3, 4.4, 5.1, 5.2, 5.3

(1.3 no design review; 2.2-2.6 no CSS/env/data/business/CI contract affected; 3.3 no E2E required — optional only; 3.5 no stress/soak; 4.1 no backend implementation — pure frontend; 4.3/4.4 no env/deploy or CI-workflow change; 5.1/5.2 no UI/visual change; 5.3 no contract review needed, zero contracts touched.)

## Clarifications or Assumptions
- Assumption: "cache" here means in-memory reuse of the already-fetched result within the live composable/page session (guarded by the existing queried.* flags), not a new persistent or cross-session cache layer. No new storage, TTL, or env flag is introduced.
- Assumption: no route, response-shape, or async-routing behavior changes — the same endpoints are called, just fewer times. If implementation reveals any need to alter a route or payload shape, this must be promoted to business-logic-change/feature-enhancement with the API/data contract path forced.
- Assumption: filter-identity comparison can be derived from the existing filter state already tracked by these composables; if a reliable equality signal does not exist and one must be constructed, that is in-scope implementation detail, not a contract change.
- Open question for implementation-planner: confirm whether the sub-tab setActiveSubTab call sites are invoked from App.vue or a child component under frontend/src/query-tool/components/; resolve via CER if the latter.

## Context Manifest Draft

### Affected Surfaces
- frontend query-tool feature module — sub-tab switching / client-side query caching

### Allowed Paths
- specs/changes/query-tool-subtab-cache/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/query-tool/composables/
- frontend/src/query-tool/App.vue
- frontend/tests/query-tool/
- frontend/tests/legacy/query-tool-composables.test.js

### Agent Work Packets

#### implementation-planner
- specs/changes/query-tool-subtab-cache/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/query-tool/composables/
- frontend/src/query-tool/App.vue

#### frontend-engineer
- specs/changes/query-tool-subtab-cache/
- frontend/src/query-tool/composables/
- frontend/src/query-tool/App.vue
- frontend/tests/query-tool/
- frontend/tests/legacy/query-tool-composables.test.js

#### test-strategist
- specs/changes/query-tool-subtab-cache/
- frontend/src/query-tool/composables/
- frontend/tests/query-tool/
- frontend/tests/legacy/query-tool-composables.test.js

#### qa-reviewer
- specs/changes/query-tool-subtab-cache/
- frontend/src/query-tool/composables/
- frontend/tests/query-tool/

### Context Expansion Requests
- none at classification time — indexes were sufficient to propose all candidate paths. App.vue is included read-only for call-site verification; if the engineer finds the sub-tab call sites live in a component under frontend/src/query-tool/components/ rather than App.vue, raise a CER to add that specific file rather than widening to the whole components/ tree.
