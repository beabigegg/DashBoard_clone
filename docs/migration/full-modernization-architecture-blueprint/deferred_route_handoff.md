# Deferred Route Handoff (Phase 1 -> Follow-up)

## Source Change

- `openspec/changes/full-modernization-architecture-blueprint/`

## Deferred Routes (Not in Phase 1 Blocking Scope)

- `/tables`
- `/excel-query`
- `/query-tool`
- `/mid-section-defect`

## Follow-up Change

- `openspec/changes/deferred-route-modernization-follow-up/`

## Handoff Content

1. Scope boundary contract:
- Source: `docs/migration/full-modernization-architecture-blueprint/route_scope_matrix.json`

2. Required acceptance model to carry forward:
- Parity fixtures/checks:
  - `docs/migration/full-modernization-architecture-blueprint/parity_golden_fixtures.json`
  - `docs/migration/full-modernization-architecture-blueprint/interaction_parity_checks.json`
- Manual acceptance + bug replay:
  - `docs/migration/full-modernization-architecture-blueprint/page_content_manual_acceptance_checklist.md`
  - `docs/migration/full-modernization-architecture-blueprint/known_bug_baseline.json`
  - `docs/migration/full-modernization-architecture-blueprint/bug_revalidation_records.json`

3. Governance policy to carry forward:
- `docs/migration/full-modernization-architecture-blueprint/quality_gate_policy.json`
- `docs/migration/full-modernization-architecture-blueprint/governance_milestones.md`
- `docs/migration/full-modernization-architecture-blueprint/asset_readiness_manifest.json`

## Transfer Rule

- Deferred routes remain excluded from phase-1 blocking criteria.
- Follow-up change MUST promote these routes to in-scope and apply equivalent parity/manual-acceptance/bug-revalidation gates before legacy retirement.
