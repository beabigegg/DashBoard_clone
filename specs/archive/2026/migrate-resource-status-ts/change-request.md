# Change Request

## Original Request

Migrate `frontend/src/resource-status/` feature app (設備即時概況) from JavaScript to TypeScript. This is Phase 3 of the project-wide TS migration plan (ts-migration-plan.md, item #19).

## Business / User Goal

Increase type-safety coverage for the resource-status app; catch prop/API-shape mismatches at compile time; align with the fully-migrated core/, shared-composables/, and shared-ui/ layers.

## Non-goals

- No runtime behavior changes
- No UI/UX changes
- No new features
- Does not migrate resource-shared/ (already TypeScript)

## Constraints

- `npm run type-check` must pass with zero errors after migration
- All `.js` import specifiers inside SFCs must drop extension (not renamed to `.ts`), per CLAUDE.md TypeScript Migration Rules
- `index.html` references `./main.js` as entry — do NOT update it (Vite resolves `main.ts` at build time)
- Any echarts callbacks annotated `// TODO: type echarts callback` per migration rules

## Known Context

- `resource-shared/constants.ts` and `resource-shared/index.ts` are already TypeScript
- `shared-ui/`, `shared-composables/`, `core/` are fully migrated TypeScript
- `FloatingTooltip.vue` imports from `../../core/api.js` — drop `.js` extension only
- API endpoints: `/api/resource/status/options`, `/api/resource/status/summary`, `/api/resource/status`

## Open Questions

(none)

## Requested Delivery Date / Priority

Now — Phase 3 migration, item #19 (lowest risk tier in the migration plan)
