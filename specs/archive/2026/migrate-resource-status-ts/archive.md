---
change-id: migrate-resource-status-ts
archived: 2026-05-13
---

# Archive — migrate-resource-status-ts

## Change Summary

Migrated `frontend/src/resource-status/` (設備即時概況 — Equipment Real-time Overview) from JavaScript to TypeScript as Phase 3, item #19 of the project-wide TypeScript migration plan — the last item in the "一般優先" tier. The migration renamed `main.js → main.ts`, added `<script setup lang="ts">` to all 7 SFCs (App.vue, EquipmentCard.vue, EquipmentGrid.vue, FilterBar.vue, StatusHeader.vue, FloatingTooltip.vue, MatrixSection.vue), declared TypeScript interfaces for all component prop/emit contracts, and expanded `frontend/tsconfig.json` to include `src/resource-status/**/*`. No behavior, template, CSS, or API change was introduced.

## Final Behavior

No behavior change. The feature app renders identically; TypeScript annotation is compile-time only. All existing Vitest and legacy node tests continued to pass (302 tests).

## Final Contracts Updated

None. Contract-reviewer verified that all 3 API endpoints (`/api/resource/status/options`, `/api/resource/status/summary`, `/api/resource/status`) remain unchanged. No contract edits were required.

## Final Tests Added / Updated

None added. Existing `resource-status.test.js` (legacy node --test) and Vitest suites passed without modification. No Python parity test files referenced `resource-status/` paths (audited during migration).

## Final CI/CD Gates

| gate | result |
|---|---|
| frontend-unit (Vitest) | PASSED — 302 tests |
| frontend-legacy (node --test) | PASSED |
| css-governance | PASSED — 0 violations |
| frontend-type-check | PASSED — 0 errors (scope expanded to src/resource-status/**/*) |
| frontend-build | PASSED (CI) |
| contract-validate | PASSED (CI) |
| cdd-strict-gate | PASSED (CI) |

## Production Reality Findings

No surprises. One notable pattern required during migration:

- **`useFilterOrchestrator` not-yet-migrated composable**: The `committed` ref returned by the JS composable was cast via `as unknown as FilterState` rather than the `@ts-expect-error` variant documented in CLAUDE.md. Both achieve the same goal (forcing TypeScript to accept the type without `any`); the double-cast form avoids a suppression comment for object-shaped returns where the error would be on the whole expression rather than a single assignment line.
- **`MatrixSection.vue` hierarchy column descriptors**: Column callbacks (`value`, `render`, `cellClass`, `isClickable`, `isSelected`, `payload`) are inherently polymorphic over `ResourceNode | FamilyNode | GroupNode`. These were typed as `unknown` with `// TODO: type hierarchy node union` annotations rather than forcing a union type that would require exhaustive type guards throughout the descriptor table.
- **`FilterBar.vue` checkbox event**: `(event.target as HTMLInputElement).checked` cast required because Vue `@change` handler receives `Event`, not `InputEvent`.

## Lessons Promoted to Standards

**Lesson A — Double-cast `as unknown as T` for not-yet-migrated composables**
- Target: `CLAUDE.md` → `## TypeScript Migration Rules`, appended to the `@ts-expect-error` bullet
- Rule: When `@ts-expect-error` would need to suppress an entire return expression, `as unknown as DeclaredInterface` is an accepted alternative — both produce a compile error once the source is migrated.
- Evidence: `frontend/src/resource-status/App.vue`

**Lesson B — Column-descriptor callbacks with polymorphic hierarchy node unions**
- Target: `CLAUDE.md` → `## TypeScript Migration Rules`, new bullet after the echarts bullet
- Rule: Column-descriptor callbacks that accept a hierarchy node union may use `(node: unknown) => ...` with `// TODO: type hierarchy node union` instead of exhaustive union guards. Do not block migration on resolving the union.
- Evidence: `frontend/src/resource-status/components/MatrixSection.vue`

## Follow-up Work

- `MatrixSection.vue` columns descriptor functions currently use `unknown` for node parameters. A follow-up could define a `MatrixNode = ResourceNode | FamilyNode | GroupNode` union and add discriminated union guards — deferred as out-of-scope for this Tier 4 migration.
- `useFilterOrchestrator` remains a `.js` composable. When it is migrated (future phase), the `as unknown as FilterState` cast in `App.vue` will produce a compile error, prompting cleanup.

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and active project guidance (`CLAUDE.md`/`CODEX.md`).
