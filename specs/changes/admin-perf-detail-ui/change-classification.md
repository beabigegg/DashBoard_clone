# Change Classification

## Change Types
- primary: ui-only-change, feature-enhancement
- secondary: data-shape (frontend rendering of new API fields)

## Risk Level
- low

## Impact Radius
- module-level (admin-dashboard SPA PerformanceTab.vue only — not admin-pages)

## Tier
- 3

## Architecture Review Required
- no
- reason: Pure additive UI rendering of already-contracted API fields. No design decisions, no module-boundary changes, no data-flow changes.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)

| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | |
| proposal.md | no | |
| spec.md | no | |
| design.md | no | architecture review not required |
| qa-report.md | no | routine pass/fail fits in agent-log |
| regression-report.md | no | additive UI; no behavior change to existing fields |
| visual-review-report.md | no | small additive markup; reviewer notes fit in agent-log |
| monkey-test-report.md | no | |
| stress-soak-report.md | no | |

## Required Contracts
- API: none (backend already returns the fields; contracts/api/api-contract.md owned by merged backend change — read-only confirmation only)
- CSS/UI: contracts/css/css-inventory.md if new authored CSS is added (flag during implementation)
- Env: none
- Data shape: none (rendering only; backend nullability already contracted)
- Business logic: none
- CI/CD: none

## Required Tests
- unit: yes — Vitest unit tests for new render logic (null handling, slowlog list, memory_limit_state object)
- contract: none
- integration: none
- E2E: none
- visual: lightweight confirmation by ui-ux-reviewer in agent-log
- data-boundary: yes — null and empty-array cases for all 6 fields (covered in unit tests)
- resilience: none
- fuzz/monkey: none
- stress: none
- soak: none

## Required Agents
- contract-reviewer (confirms API shape matches contracts/api/api-contract.md; checks css-inventory if CSS added)
- test-strategist (writes test-plan.md)
- ci-cd-gatekeeper (writes ci-gates.md)
- implementation-planner (writes implementation-plan.md)
- frontend-engineer (implements rendering + Vitest unit tests in TDD)
- ui-ux-reviewer (layout, null-state display, accessibility)
- qa-reviewer (release readiness)

## Inferred Acceptance Criteria
- AC-1: When `data.redis.evicted_keys` and `data.redis.expired_keys` are integers, the performance-detail view renders both in the Redis section.
- AC-2: When `data.redis.mem_fragmentation_ratio` is a float, the view renders it (≤2 decimal places) in the Redis section.
- AC-3: When `data.redis.slowlog` is a non-empty array of `{id, duration_us, command}`, the view renders each entry; when null or empty, renders a graceful placeholder.
- AC-4: When `data.duckdb.temp_dir_bytes` is an integer, the view renders it (human-readable bytes acceptable) in a DuckDB section.
- AC-5: When `data.duckdb.memory_limit_state` is a string (e.g. `"512MB"`), the view renders the string value; when null, renders a graceful placeholder.
- AC-6: For every one of the 6 fields, when the API returns `null`, the view renders a graceful placeholder (e.g. "N/A") and does not throw, log a console error, or break sibling sections.
- AC-7: No existing fields rendered by the performance-detail view regress (additive change only).
- AC-8: No contract files are modified by this change (API shape already contracted by fix-admin-dashboard).

## Tasks Not Applicable
- not-applicable: 1.3, 4.1, 6.4

## Clarifications or Assumptions
- Assumption: Target component file lives under `frontend/src/admin-pages/` (exact path identified by frontend-engineer during implementation).
- Assumption: Rendering uses existing Tailwind tokens and shared-ui primitives. If new authored CSS is introduced, css-inventory.md must be updated and `npm run css:check` added to ci-gates.md.
- Assumption: Null-handling display text ("N/A" vs "unavailable") is a UI-copy choice deferred to ui-ux-reviewer.
- Assumption: Frontend type definitions for performance-detail may need additive update under `frontend/src/` if not yet reflecting the 6 new fields.
