## 1. Spec and strategy baseline alignment

- [x] 1.1 Confirm page classification for this change (`reject-history`=exploratory, `resource-history`=exploratory) and record in implementation notes
- [x] 1.2 Verify filter behavior baseline (debounce, stale-response guard, prune, apply/clear semantics) is mapped to concrete frontend responsibilities

## 2. Reject History interdependent options hardening

- [x] 2.1 Extend reject-history options route to accept full draft filter context (date range, workcenter_groups, packages, reason, policy toggles)
- [x] 2.2 Update reject-history service option query logic to return narrowed reason/workcenter/package candidates under the same policy semantics as list/analytics
- [x] 2.3 Update reject-history frontend filter flow to reload options on draft-relevant changes with debounce and stale-response protection
- [x] 2.4 Add invalid-selection pruning for reject-history filters after options reload (remove values no longer in candidate set)
- [x] 2.5 Ensure apply/query and export requests only use committed valid filters

## 3. Resource History interdependent filtering hardening

- [x] 3.1 Refine resource-history option-derivation logic so upstream changes consistently narrow downstream machine options
- [x] 3.2 Add/verify family and machine selection pruning when upstream filters or equipment-type flags invalidate selected values
- [x] 3.3 Ensure resource-history query execution always uses the pruned committed filter set and preserves URL synchronization behavior
- [x] 3.4 Verify first-load filter usability (options and machine candidates usable before first query)

## 4. Shared UX consistency and guardrails

- [x] 4.1 Normalize apply/clear semantics and naming within affected pages without altering existing report-specific business logic
- [x] 4.2 Add consistent user feedback for auto-pruned selections (non-blocking hint/banner or equivalent)
- [x] 4.3 Confirm debounce interval and request-token guard values are documented and consistent with project conventions

## 5. Tests and validation

- [x] 5.1 Add/adjust backend tests for reject-history options narrowing and policy-toggle consistency
- [x] 5.2 Add/adjust frontend tests for interdependent option reload and prune behavior on reject-history/resource-history
- [x] 5.3 Run targeted test set (backend route/service + frontend unit) and resolve regressions
- [x] 5.4 Run frontend build validation and verify no behavior regressions on released pages outside this scope

## 6. Rollout and regression checks

- [x] 6.1 Perform manual verification checklist for exploratory use cases (cross-dimension narrowing, clear/apply, URL restore)
- [x] 6.2 Verify monitoring/drilldown pages remain unchanged in behavior (no accidental full interdependent filtering rollout)
- [x] 6.3 Prepare release note entry describing filter strategy hardening scope and non-goals
