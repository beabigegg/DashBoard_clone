## Context

The project has completed the no-iframe shell migration and fluid shell Phase 1, but frontend modernization remains fragmented across routing governance, styling ownership, and quality enforcement.

Current state:
- Shell contract currently governs a subset of report routes, and route governance is implemented through `frontend/src/portal-shell/routeContracts.js` + `nativeModuleRegistry.js`.
- Multiple page families still ship page-global CSS patterns (`:root`, `body`, page-level max-width wrappers), creating style ownership ambiguity and cross-page leakage risk.
- Existing specs still preserve fallback-era assumptions in several areas (runtime fallback continuity and coexistence-oriented style policy).

Scope decisions for this change:
- In scope: admin surfaces `/admin/pages`, `/admin/performance`.
- Out of scope (follow-up change): `/tables`, `/excel-query`, `/query-tool`, `/mid-section-defect`.

Stakeholders:
- Frontend platform owners (shell/routing/design system)
- Report page module owners
- Backend maintainers for route serving and release gates
- QA/operations for release readiness and rollback governance

## Goals / Non-Goals

**Goals:**
- Define a shell-first canonical frontend architecture for in-scope routes with explicit route governance.
- Converge style architecture from permissive coexistence to enforceable isolation + token semantics.
- Modernize in-scope page content (charts, filters, interactions) with contract-first parity validation to prevent architecture drift during migration.
- Replace runtime fallback dependency for in-scope modules with build/deploy readiness gates.
- Add modernization-grade quality gates (behavioral, visual, accessibility, performance).
- Provide phased migration and rollback-safe program governance.

**Non-Goals:**
- Implementing code changes in this artifact phase.
- Rewriting excluded routes (`/tables`, `/excel-query`, `/query-tool`, `/mid-section-defect`) in this change.
- Replacing backend business APIs or changing report data semantics.
- Introducing mandatory framework rewrites for all pages in one release window.

## Decisions

### D1. Route Scope Matrix with Explicit Inclusion/Exclusion

**Decision:** Define an explicit route matrix for modernization enforcement.

- Included: in-scope shell-governed report routes + `/admin/pages`, `/admin/performance`.
- Excluded for follow-up: `/tables`, `/excel-query`, `/query-tool`, `/mid-section-defect`.

**Rationale:** Prevent uncontrolled scope creep while still addressing governance gaps for admin functionality.

**Alternatives considered:**
- Modernize all routes at once: rejected due to high blast radius and schedule risk.
- Only modernize report routes, defer admin pages: rejected because admin navigation governance remains inconsistent.

### D2. Canonical Shell Routing Policy for In-Scope Report Routes

**Decision:** In-scope report routes MUST have a canonical shell entry path and contract metadata. Direct route entry remains available only through explicit compatibility policy.

**Rationale:** Removes ambiguity between direct route behavior and shell-governed behavior; improves observability and testability.

**Alternatives considered:**
- Keep dual-mode indefinitely (direct vs shell): rejected due to long-term drift risk.

### D3. Admin Surfaces Become First-Class Contracted Navigation Targets

**Decision:** `/admin/pages` and `/admin/performance` are governed as explicit shell navigation targets with visibility and access policy, while retaining server authority for auth/session.

**Rationale:** Admin actions are part of platform governance and must be consistently modeled in route and visibility contracts.

### D4. Style Convergence Policy: Isolation + Token Enforcement

**Decision:** Move from "Tailwind and legacy CSS coexistence" to "controlled convergence":
- In-scope modules MUST avoid page-global selectors (`:root`, `body`) for page-local concerns.
- Shared semantics MUST be token-driven through `frontend/src/styles/tailwind.css` and shared UI layers.
- Legacy CSS usage in in-scope routes requires explicit exception policy.

**Rationale:** Reduces style collisions and maintenance overhead from fragmented style ownership.

### D5. Asset Readiness Over Runtime Fallback for In-Scope Modules

**Decision:** In-scope modules require build/deploy readiness guarantees; runtime fallback is no longer primary resilience strategy for these routes.

**Rationale:** Runtime fallback hides release failures and delays detection. Fail-fast at build/release is safer for correctness and easier to operate.

### D6. Modernization Quality Gates as Release Contract

**Decision:** Define mandatory route-level acceptance gates:
- Functional behavior parity
- Visual regression checks for critical states
- Accessibility checks (keyboard semantics, reduced-motion compatibility, landmark/label quality)
- Performance budgets (bundle and runtime thresholds)

**Rationale:** Architecture convergence without quality gates causes unstable rollouts and regressions.

### D7. Contract-First Page-Content Migration for Charts and Filters

**Decision:** In-scope chart/filter/page-content migration MUST follow a contract-first flow with reversible rollout:
- Freeze per-route content contracts before refactor (filter input semantics, query payload structure, chart data shape, interaction events, empty/error states).
- Implement a parity harness using golden fixtures and critical-state comparisons before switching default rendering.
- Cut over with route-scoped feature flags and immediate rollback controls (no irreversible flip in one step).
- Progress route-by-route only after manual acceptance sign-off is completed for the current route.
- Remove legacy content implementation only after parity checks and manual acceptance sign-off are completed.

**Rationale:** Prior migration failures were caused by implementation-first rewrites without strict parity and rollback controls, leading to layout/interaction drift and hard-to-debug regressions.

### D8. Mandatory "BUG Revalidation During Migration" Gate

**Decision:** Each route modernization MUST include explicit BUG revalidation before sign-off:
- Create a route-level known-bug baseline (within migrated scope: chart, filter, and page interaction behavior) before implementation.
- During manual acceptance, replay known-bug checks on the modernized route.
- If a known legacy bug is reproduced in the modernized implementation, route sign-off MUST fail and cutover/legacy-retirement MUST be blocked until fixed.

**Rationale:** Parity-only migration can accidentally preserve old defects. The modernization objective is not only structural migration, but also preventing legacy defect carry-over into the new architecture.

## Risks / Trade-offs

- **[Scope ambiguity]** Route inclusion can drift during execution. → Mitigation: publish a frozen in-scope/out-of-scope matrix in specs and tasks.
- **[Admin integration complexity]** Admin routes have different auth/session behavior than report modules. → Mitigation: keep backend auth authority unchanged; only modernize navigation contract layer in this change.
- **[Temporary dual standards]** Excluded routes still use legacy conventions. → Mitigation: explicit follow-up change linkage and governance deadline.
- **[Release friction increase]** Fail-fast asset readiness can block releases more often initially. → Mitigation: phased enforcement with warning mode then blocking mode.
- **[Style migration churn]** Token/isolation enforcement may require broad CSS refactor in in-scope pages. → Mitigation: staged rollout by route family and exception registry.
- **[Content migration instability]** Chart/filter rewrites can regress data semantics or interaction flows. → Mitigation: contract freeze + golden fixture parity + page-by-page manual acceptance + feature-flagged cutover with rollback.
- **[Legacy bug carry-over]** Modernized routes can pass parity yet still replicate known legacy defects. → Mitigation: mandatory per-route bug baseline and replay checks as blocking sign-off criteria.

## Migration Plan

1. Publish and freeze modernization scope matrix (included/excluded routes).
2. Define delta specs for route governance, style enforcement, quality gates, and asset readiness retirement policy.
3. Derive implementation tasks in phased waves (governance first, then style convergence, then gate enforcement).
4. Publish page-content contracts and golden fixtures for in-scope routes before chart/filter cutover.
5. Record route-level known-bug baselines for migrated scope and attach them to acceptance checklists.
6. Execute page-by-page manual acceptance sign-off (including bug replay checks) and only then move to the next route.
7. Enable non-blocking observability checks first (dry-run mode), then switch to blocking gates.
8. Roll out per route family with rollback criteria and runbook updates.
9. Open follow-up modernization change for excluded routes.

## Rollback Strategy

- Maintain reversible config switches for new quality gates during initial adoption.
- If blocking gates cause production-impacting false positives, revert gate mode to warning while preserving telemetry.
- Keep route-level rollback path documented for each in-scope family.
- Keep per-route manual acceptance records so rollback decisions can reference concrete pass/fail evidence.
- Keep per-route bug baseline and bug-replay results so cutover and rollback decisions can prove legacy bug non-carry-over.

## Open Questions

- Should admin pages remain backend-rendered targets with shell-managed links only, or move to shell-native view composition in a later phase?
- Which visual regression toolchain should be standardized (existing snapshot evidence extension vs dedicated UI visual diff pipeline)?
- What are initial enforceable performance thresholds for route bundles and shell startup latency?
- Should parity harness for charts use DOM-level snapshots only, or also include canonicalized data-level assertions as a blocking gate?
