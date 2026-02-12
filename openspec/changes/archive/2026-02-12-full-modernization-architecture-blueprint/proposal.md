## Why

The project has completed the critical iframe-to-Vue migration and Phase 1 shell fluidization, but the frontend architecture is still only partially modernized. Several routes remain outside shell contract governance, style ownership is still fragmented across page-local global CSS (`:root`, `body`, page-level `max-width`), and fallback-era patterns remain in docs and runtime expectations.

A full modernization blueprint is needed now to converge the system into a single, predictable frontend architecture before more feature work increases divergence and maintenance cost.

## What Changes

- Establish a shell-first architecture baseline where in-scope routes are contract-governed and module-registered with deterministic route visibility and ownership metadata.
- **BREAKING**: Retire legacy runtime fallback expectations for primary report routes in favor of build-readiness and deploy gating (fail-fast in CI/release instead of runtime degraded UX).
- **BREAKING**: Adopt canonical shell routing policy for report pages (legacy direct-entry routes become explicit compatibility redirects with sunset policy).
- Standardize style architecture: remove page-level global CSS side effects, enforce scoped styling boundaries, and converge to token-first Tailwind design primitives.
- Define contract-first page-content modernization for in-scope routes (charts, filters, and page interactions) with parity checkpoints before cutover.
- Use page-by-page manual acceptance sign-off as the required readiness gate for content migration progression.
- Enforce mandatory "BUG revalidation during migration" for each route so known legacy bugs in migrated scope SHALL NOT be carried into the new architecture.
- Introduce modernization quality gates covering interaction behavior, visual regressions, accessibility, and performance budgets.
- Define phased execution and rollback-safe governance for “full modernization” as a program (not a single code patch), including explicit completion criteria and deprecation milestones.
- Include admin surfaces in this change scope: `/admin/pages` and `/admin/performance` SHALL be first-class shell-governed routes with explicit contract metadata and visibility policy.
- Defer the following routes to a subsequent change (out of scope for this change): `/tables`, `/excel-query`, `/query-tool`, `/mid-section-defect`.

## Capabilities

### New Capabilities
- `frontend-platform-modernization-governance`: Defines target frontend architecture, phased milestones, modernization guardrails, and deprecation policy.
- `unified-shell-route-coverage`: Ensures in-scope routes (including admin pages/performance) are covered by shell route contracts, loader registry, and navigation visibility rules with CI blocking on gaps.
- `style-isolation-and-token-enforcement`: Enforces CSS scope boundaries and token-first style semantics; eliminates page-global style leakage patterns.
- `page-content-modernization-safety`: Governs chart/filter/page-content migration with contract baselines, parity verification, legacy bug carry-over prevention, and reversible rollout controls.
- `frontend-quality-gate-modernization`: Adds behavioral, visual, accessibility, and performance acceptance gates for route-level changes.
- `asset-readiness-and-fallback-retirement`: Defines build/deploy guarantees and controlled retirement of runtime fallback-era behavior.

### Modified Capabilities
- `spa-shell-navigation`: Extend from current native route-view baseline to full route coverage, canonical shell routing, and contract completeness enforcement.
- `tailwind-design-system`: Shift from coexistence-with-legacy to convergence-and-enforcement with explicit legacy CSS deprecation rules.
- `full-vite-page-modularization`: Tighten from “fallback continuity” to “asset readiness governance” with stronger release-time guarantees.
- `vue-vite-page-architecture`: Update route serving expectations to shell-first canonical model with explicit compatibility redirects and sunset criteria.

## Impact

- **Frontend shell and routing**: `frontend/src/portal-shell/` (`App.vue`, `router.js`, `routeContracts.js`, `nativeModuleRegistry.js`, navigation metadata handling).
- **Frontend page style system**: `frontend/src/*/style.css`, `frontend/src/*/styles.css`, `frontend/src/styles/tailwind.css`, shared UI/style modules.
- **Frontend page-content modules**: chart, filter, and page interaction modules under `frontend/src/**` used by in-scope routes, including compatibility adapters where needed.
- **Backend route serving and compatibility**: Flask route handlers that serve page entries and legacy direct-entry paths, plus deploy-time asset-readiness checks.
- **Quality system**: `frontend/tests/`, Python integration tests, and potential new CI checks for visual/a11y/performance budgets.
- **Documentation and operations**: migration/runbook docs, architecture maps, and release governance docs aligned to modernization milestones.
- **Dependencies/tooling**: likely introduction of additional frontend QA tooling in dev workflow (subject to design artifact decisions).
- **Scope boundary note**: this change explicitly excludes `/tables`, `/excel-query`, `/query-tool`, `/mid-section-defect`; those routes are planned for a follow-up modernization change.
