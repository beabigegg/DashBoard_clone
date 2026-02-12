# Page Content Manual Acceptance Checklist

## Rule

- Route cutover proceeds one route at a time.
- Next route cutover is blocked until current route is manually signed off.
- Legacy code retirement is blocked until parity checks and manual sign-off are both complete.

## Mandatory Checks Per Route

1. Filter semantics match baseline (apply, reset, URL/query continuity).
2. Chart interactions match baseline (drill/selection/clear behavior).
3. Empty/loading/error/success states are correct and non-overlapping.
4. Table/chart linked interactions remain deterministic.
5. Accessibility: keyboard flow, focus visibility, `aria-*` semantics, reduced-motion behavior.
6. Known-bug replay checks completed (see `known_bug_baseline.json`).
7. No reproduced legacy bug in migrated scope.

## Sign-Off Template

- Route:
- Owner:
- Reviewer:
- Date:
- Parity evidence links:
- Known-bug replay result:
- Blocking defects:
- Decision: `approved` | `rework-required`
