# OpenSpec Archive Readiness (`portal-no-iframe-navigation`)

## Spec Sync Scope

Main specs synchronized/updated for this change:

- `openspec/specs/full-vite-page-modularization/spec.md`
- `openspec/specs/portal-drawer-navigation/spec.md`
- `openspec/specs/vue-vite-page-architecture/spec.md`
- `openspec/specs/migration-gates-and-rollout/spec.md`
- `openspec/specs/spa-shell-navigation/spec.md` (new)
- `openspec/specs/tailwind-design-system/spec.md` (new)
- `openspec/specs/frontend-motion-system/spec.md` (new)
- `openspec/specs/legacy-page-wrapper-strategy/spec.md` (new)

## Migration Closure Artifacts

- Rewrite smoke checklist:
  - `docs/migration/portal-no-iframe/legacy_rewrite_smoke_checklists.md`
- Rewrite exemplar:
  - `docs/migration/portal-no-iframe/tmtt_rewrite_exemplar.md`
- Rewrite playbook:
  - `docs/migration/portal-no-iframe/legacy_rewrite_playbook.md`
- Wrapper decommission record:
  - `docs/migration/portal-no-iframe/wrapper_decommission_report.md`
- Frame field retirement record:
  - `docs/migration/portal-no-iframe/frame_id_tool_src_deprecation_plan.md`

## Pre-Archive Checklist

- [x] `openspec validate portal-no-iframe-navigation --strict` passes.
- [x] Build and core migration tests pass on latest branch.
- [x] Task list in `openspec/changes/portal-no-iframe-navigation/tasks.md` is fully checked.
