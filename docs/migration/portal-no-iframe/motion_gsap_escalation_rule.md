# GSAP Escalation Rule

## Default

Use Vue native transitions and CSS transitions for portal migration work.

## GSAP allowed only when all conditions are true

1. Interaction cannot be expressed with native Vue/CSS transitions without major maintainability cost.
2. Animation is business-critical (e.g., complex timeline playback or synchronized multi-chart storytelling).
3. Reduced-motion fallback is explicitly implemented.
4. Performance impact is measured on target hardware and meets baseline thresholds.
5. A rollback switch exists to disable advanced animation without breaking functionality.

## Approval checklist

- Document the exact scenario and why Vue/CSS is insufficient.
- Add test coverage for degraded/non-animated path.
- Confirm bundle-size impact is acceptable for the target route.
