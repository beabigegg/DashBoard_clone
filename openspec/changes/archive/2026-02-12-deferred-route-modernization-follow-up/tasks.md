## 1. Scope and Governance Freeze

- [x] 1.1 Publish frozen in-scope matrix for `/tables`, `/excel-query`, `/query-tool`, `/mid-section-defect`
- [x] 1.2 Define completion criteria, deprecation milestones, and exception registry updates for deferred-route phase
- [x] 1.3 Record explicit upstream linkage to `full-modernization-architecture-blueprint` handoff artifacts
- [x] 1.4 Add deferred-route pre-change confirmation template and required fields (status snapshot, contract baseline refs, known-bug baseline ref, rollback flag plan)
- [x] 1.5 Record scope boundary note that deferred/dev routes are in-scope for this change and released-only restriction does not apply

## 2. Shell Route Contract Completion

- [x] 2.1 Promote deferred routes to in-scope in shell route contracts with complete metadata
- [x] 2.2 Implement governed navigation targets and visibility policy validation for all deferred routes
- [x] 2.3 Add CI-blocking checks for missing deferred-route contract metadata in this phase

## 3. Canonical Routing and Compatibility

- [x] 3.1 Define canonical shell entry behavior for each deferred route
- [x] 3.2 Implement explicit compatibility policy for direct non-canonical entry with query continuity
- [x] 3.3 Add integration tests for canonical redirect and compatibility semantics

## 4. Page-Content Modernization Safety

- [x] 4.0 Before each route implementation starts, record and approve route-scoped pre-change confirmation
- [x] 4.1 Define per-route content contracts (filter semantics, payload, chart/table shape, state transitions)
- [x] 4.2 Build golden fixtures and interaction parity checks for each deferred route
- [x] 4.3 Add route-scoped feature flags and rollback controls for deferred-route cutover
- [x] 4.4 Define and enforce per-route manual acceptance checklist and sign-off records
- [x] 4.5 Record known-bug baselines before implementation and require bug replay during acceptance
- [x] 4.6 Block sign-off and legacy retirement when known bugs reproduce on modernized routes

## 5. Asset Readiness and Fallback Retirement

- [x] 5.1 Extend asset-readiness manifest/checks to deferred routes
- [x] 5.2 Enforce fail-fast release behavior when deferred-route assets are missing
- [x] 5.3 Retire deferred-route runtime fallback posture per governance milestones

## 6. Quality Gates, CI, and Rollout

- [x] 6.1 Extend functional/visual/accessibility/performance gates to deferred routes
- [x] 6.2 Wire CI jobs for route governance, quality gates, and readiness checks for deferred scope
- [x] 6.3 Update rollout runbook, rollback controls, and observability checkpoints for deferred-route cutover
