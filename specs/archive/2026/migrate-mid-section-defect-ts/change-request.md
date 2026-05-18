# Change Request

## Original Request

Migrate the mid-section-defect page from JavaScript to TypeScript (Phase 3 migration). Rename all `.js` files to `.ts`, add proper TypeScript types, ensure `vue-tsc --noEmit` passes with the app in scope, and update `tsconfig.json` `include` accordingly.

## Business / User Goal

Continue the project-wide Phase 3 TypeScript migration. `mid-section-defect` is one of the remaining JS apps listed in `CLAUDE.md`. Full TS coverage improves compile-time safety and aligns the app with the already-migrated feature apps.

## Non-goals

- No functional/business logic changes
- No UI redesign
- No new features

## Constraints

- Must follow Phase 3 migration rules in `CLAUDE.md` (TypeScript Migration Rules section)
- Must audit all Python test files for hardcoded `.js` paths
- Must audit Vitest test files that load any renamed file
- Must NOT touch `index.html` Vite entry (`./main.js` is intentional)
- Must bump `contracts/ci/ci-gate-contract.md` with `### frontend-type-check scope expansion` note
- Must add matching entry to `contracts/CHANGELOG.md`
- Node ≥22.6 required for parity tests

## Known Context

- Phase 3 remaining JS apps per CLAUDE.md: `admin-dashboard`, `admin-performance`, `admin-user-usage-kpi`, `anomaly-overview`, `mid-section-defect`, `portal`, `portal-shell`, `tables`
- Established migration pattern in: `migrate-material-trace-ts` (most recent completed Phase 3)
- MultiSelect.vue used by mid-section-defect — any prop/emit changes must be additive

## Open Questions

None

## Requested Delivery Date / Priority

Normal — no deadline specified
