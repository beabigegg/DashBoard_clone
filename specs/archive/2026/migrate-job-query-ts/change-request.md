# Change Request

## Original Request

Migrate `frontend/src/job-query` from JavaScript to TypeScript.
Affected files: `main.js`, `composables/useJobQueryData.js`, `App.vue`.

## Business / User Goal

Continue the incremental TypeScript migration of the MES Dashboard frontend. The `job-query` feature app is one of the remaining JavaScript-only feature directories. Migrating it brings it in line with already-migrated modules (`core/`, `shared-composables/`, `shared-ui/`, `resource-history/`, etc.) and ensures type safety, IDE autocomplete, and compile-time error detection for this surface.

## Non-goals

- No functional changes to job-query behavior.
- No migration of other feature apps beyond `job-query`.
- No changes to backend Python code.

## Constraints

- Must follow the TypeScript migration rules documented in `CLAUDE.md` (TS migration section).
- `npm run type-check` must pass after migration (vue-tsc --noEmit).
- Existing Vitest tests must continue to pass.
- Node ≥22.6 required (already pinned in `environment.yml`).
- `index.html` entry point references `./main.js` — do NOT rename; Vite resolves `.ts` at build time.

## Known Context

- Prior phases completed: `core/` (Phase 1a), `shared-composables/` (Phase 1b), `shared-ui/` (Phase 1c), `resource-history/` (Phase 3, most recent).
- CLAUDE.md TypeScript Migration Rules provide the exact patterns to follow (declared-interface + @ts-expect-error, barrel audit, .js specifier drops, echarts TODO annotations).
- `useJobQueryData.js` is a composable — pattern mirrors `useAutoRefresh.ts` / `useAutocomplete.ts` from Phase 1b.

## Open Questions

None — migration pattern is established from prior phases.

## Requested Delivery Date / Priority

Normal priority. No deadline.
