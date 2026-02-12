## 1. Scope and Governance Freeze

- [ ] 1.1 Publish frozen in-scope matrix for `/tables`, `/excel-query`, `/query-tool`, `/mid-section-defect`
- [ ] 1.2 Define completion criteria, deprecation milestones, and exception registry updates for deferred-route phase
- [ ] 1.3 Record explicit upstream linkage to `full-modernization-architecture-blueprint` handoff artifacts

## 2. Shell Route Contract Completion

- [ ] 2.1 Promote deferred routes to in-scope in shell route contracts with complete metadata
- [ ] 2.2 Implement governed navigation targets and visibility policy validation for all deferred routes
- [ ] 2.3 Add CI-blocking checks for missing deferred-route contract metadata in this phase

## 3. Canonical Routing and Compatibility

- [ ] 3.1 Define canonical shell entry behavior for each deferred route
- [ ] 3.2 Implement explicit compatibility policy for direct non-canonical entry with query continuity
- [ ] 3.3 Add integration tests for canonical redirect and compatibility semantics

## 4. Page-Content Modernization Safety

- [ ] 4.1 Define per-route content contracts (filter semantics, payload, chart/table shape, state transitions)
- [ ] 4.2 Build golden fixtures and interaction parity checks for each deferred route
- [ ] 4.3 Add route-scoped feature flags and rollback controls for deferred-route cutover
- [ ] 4.4 Define and enforce per-route manual acceptance checklist and sign-off records
- [ ] 4.5 Record known-bug baselines before implementation and require bug replay during acceptance
- [ ] 4.6 Block sign-off and legacy retirement when known bugs reproduce on modernized routes

## 5. Asset Readiness and Fallback Retirement

- [ ] 5.1 Extend asset-readiness manifest/checks to deferred routes
- [ ] 5.2 Enforce fail-fast release behavior when deferred-route assets are missing
- [ ] 5.3 Retire deferred-route runtime fallback posture per governance milestones

## 6. Quality Gates, CI, and Rollout

- [ ] 6.1 Extend functional/visual/accessibility/performance gates to deferred routes
- [ ] 6.2 Wire CI jobs for route governance, quality gates, and readiness checks for deferred scope
- [ ] 6.3 Update rollout runbook, rollback controls, and observability checkpoints for deferred-route cutover
