# Pre-Change Confirmation Template (Deferred Route)

## Rule

Before any implementation work begins on a deferred route, a route-scoped pre-change confirmation MUST be recorded and approved. Implementation is BLOCKED until confirmation exists.

## Required Fields

1. **Route**: The deferred route path (e.g., `/tables`).
2. **Status Snapshot**: Current route status in page registry (e.g., `dev`, `released`).
3. **Scope Boundary Check**: Confirmation that the route is listed in `route_scope_matrix.json` as in-scope for this change.
4. **Contract Baseline Refs**: References to existing route contracts and content contracts that define expected behavior.
5. **Known-Bug Baseline Ref**: Reference to `known_bug_baseline.json` entry for this route (or confirmation that baseline is initialized).
6. **Rollback Flag Plan**: Planned feature flag key and rollback strategy for this route's cutover.
7. **Owner**: The person/team responsible for this route's modernization.
8. **Date**: Date of confirmation.
9. **Approved By**: Reviewer who approved the pre-change confirmation.

## Template

```
Route: /<route-name>
Status Snapshot: <dev|released>
Scope Boundary Check: confirmed in route_scope_matrix.json as in-scope
Contract Baseline Refs:
  - Route contract: route_contracts.json#/<route-name>
  - Content contract: route_content_contracts.json#/<route-name>
Known-Bug Baseline Ref: known_bug_baseline.json#/<route-name>
Rollback Flag Plan:
  - Feature flag: modernization_feature_flags.json#/<route-name>.content_cutover_enabled
  - Rollback strategy: fallback_to_legacy_route
Owner: <owner>
Date: <YYYY-MM-DD>
Approved By: <reviewer>
```
