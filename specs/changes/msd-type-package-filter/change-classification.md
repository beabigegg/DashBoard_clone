# Change Classification

## Change Types
- primary: `feature-add` (api-add + ui-add — new filter dimensions for mid-section-defect)
- secondary: `api-only-change` (new endpoint + new analysis params), `ui-only-change` (FilterBar MultiSelects)

## Risk Level
- medium

## Impact Radius
- module-level (mid-section-defect feature: backend route/service + frontend app; reuses existing `container_filter_cache`)

## Tier
- 2

## Architecture Review Required
- no
- reason: all design decisions are pre-made and confirmed in the change request — no Oracle SQL change, Python post-query filtering, no Redis cache-key change, no migration, reuse of existing `container_filter_cache` 24h TTL. No module-boundary, data-flow, or rollback decision remains open.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)

| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | additive feature; current baseline (no Type/Package filter) captured in AC-5 |
| proposal.md | no | scope and decisions already fixed in change-request |
| spec.md | no | no separate product investigation needed |
| design.md | no | Architecture Review not required |
| qa-report.md | no | routine; use agent-log/qa-reviewer.yml pointer unless blocking finding arises |
| regression-report.md | no | no existing-behavior change; AC-5 covers no-filter parity via tests |
| visual-review-report.md | no | new MultiSelects reuse shared component; record in agent-log/visual-reviewer.yml |
| monkey-test-report.md | no | not applicable |
| stress-soak-report.md | no | filtering is in-memory post-query; no new load surface |

## Required Contracts
- API: yes — new `GET /api/mid-section-defect/container-filter-options`; new `pj_types`/`packages` query params on analysis endpoint. Update `contracts/api/api-contract.md`, `contracts/api/api-inventory.md`, and regenerate BOTH `contracts/openapi.json` AND `contracts/api/openapi.json`.
- CSS/UI: minor — only if new authored CSS source is introduced. Confirm in 2.2; likely no css-inventory change.
- Env: no
- Data shape: yes — filter-options response shape + analysis response remains shape-stable under filtering. Update `contracts/data/data-shape-contract.md`.
- Business logic: no
- CI/CD: no

## Required Tests
- unit: yes — service-layer Python `pj_types`/`packages` filtering of `detection_df`; route param parsing/forwarding (per-kwarg assertions, both selected/empty cases)
- contract: yes — new endpoint + new params; capture sample for `get_mid_section_defect_container_filter_options`; assert analysis response shape unchanged
- integration: yes — `container-filter-options` proxies `container_filter_cache.get_filter_options()` without hitting Oracle (cache-hit path)
- E2E: yes — Playwright: render both MultiSelects, apply Type/Package, assert narrowed results
- visual: yes (light) — FilterBar renders two new controls without layout break; evidence via agent-log
- data-boundary: yes — malformed/empty/unknown `pj_types`/`packages` values; option payload with empty/duplicate tuples
- resilience: optional — Redis cache miss / `container_filter_cache` unavailable falls back gracefully (no 5xx)
- fuzz/monkey: no
- stress: no
- soak: no

## Required Agents
- `contract-reviewer` — API + data-shape contract conformance, openapi sync (before implementation)
- `test-strategist` — AC → test mapping, data-boundary and cross-filter coverage
- `implementation-planner` — execution packet after contracts + test plan are ready
- `backend-engineer` — new route + service post-query filtering, `container_filter_cache` reuse
- `frontend-engineer` — FilterBar MultiSelects, App.vue `pjTypes`/`packages` state, cross-filter linkage
- `ui-ux-reviewer` — new filter controls, cross-filter interaction, accessibility/keyboard focus
- `visual-reviewer` — render evidence for the two new selects
- `qa-reviewer` — release readiness

## Inferred Acceptance Criteria
- AC-1: `GET /api/mid-section-defect/container-filter-options` returns Type (`PJ_TYPE`) and Package (`PRODUCTLINENAME`) option sets sourced from `container_filter_cache.get_filter_options()`, without issuing any Oracle query.
- AC-2: The analysis endpoint accepts `pj_types` and `packages` parameters and applies them as a post-query filter on `detection_df` (Python/DataFrame layer) before aggregation.
- AC-3: FilterBar.vue renders two new MultiSelect controls (Type, Package) and App.vue `filters` state includes `pjTypes` and `packages`.
- AC-4: Cross-filter linkage works: selecting Type(s) narrows the available Package options (and vice versa), consistent with production-history `useFirstTierFilters` behavior.
- AC-5: With no Type/Package selected, analysis output is identical to current behavior (no regression).
- AC-6: Filter options are served from the existing 24h-TTL Redis cache; no new cache namespace or Redis key structure is introduced.
- AC-7: Empty, unknown, or malformed `pj_types`/`packages` values are handled gracefully (no 5xx; sensible empty/full result); analysis response shape is unchanged.

## Tasks Not Applicable
- not-applicable: 1.3, 2.3, 2.5, 2.6, 3.5, 4.3, 4.4

## Clarifications or Assumptions
- `station_detection.sql` outputs both `PJ_TYPE` and `PRODUCTLINENAME` (confirmed by pre-classification read). Post-query filtering on `detection_df` is the implementation path.
- The new filter-options endpoint returns the same option structure already produced by `container_filter_cache` for production-history; data-shape contract entry should reference that shape rather than redefining it.
- No feature flag gates this change; it ships enabled.
