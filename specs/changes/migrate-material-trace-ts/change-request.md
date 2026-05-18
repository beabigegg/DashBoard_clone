# Change Request

## Original Request

Migrate the material-trace page from JavaScript to TypeScript (Phase 3 per-app TS migration).

## Business / User Goal

Complete Phase 3 TypeScript migration for the material-trace feature app, bringing it in line with already-migrated apps (wip, hold, resource, production-history, etc.). Improves type safety, IDE support, and eliminates JS-only escape hatches in this module.

## Non-goals

- Refactoring material-trace business logic beyond what TS requires
- Migrating other feature apps (this change covers material-trace only)
- Adding new features or changing MES query behavior

## Constraints

- Must not break existing tests or MES data flow
- Python parity tests (`tests/test_frontend_*_parity.py`) reference file paths — must update for `.ts` extensions
- Each feature app's `index.html` references `./main.js` as Vite entry — do NOT update (Vite resolves `main.ts` at build time)
- `vi.mock('...file.js')` static mock paths resolve transparently after rename — do NOT update static mock specifiers
- Node ≥ 22.6 required for `--experimental-strip-types` used in parity tests

## Known Context

- Phase 3 TS migration pattern established in CLAUDE.md (TypeScript Migration Rules section)
- material-trace is one of the remaining JS apps: admin-dashboard, admin-performance, admin-user-usage-kpi, anomaly-overview, material-trace, mid-section-defect, portal, portal-shell, tables
- Vitest `include` must cover `src/**/*.test.ts` for SFC-paired tests
- CSS must be scoped under `.theme-<name>` per Portal-Shell CSS Architecture Notes

## Open Questions

None — migration pattern is well-established from prior Phase 3 changes.

## Requested Delivery Date / Priority

Normal priority; no hard deadline.
