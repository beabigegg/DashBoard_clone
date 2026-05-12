# Change Request

## Original Request

Migrate `frontend/src/admin-shared/` to TypeScript (Phase 2 of the project-wide TypeScript migration). All `.js` source files should become `.ts`; Vue SFCs should gain `<script lang="ts">`. The change is complete when `npm run type-check` passes for the `admin-shared/` scope and existing tests remain green.

## Business / User Goal

Bring `admin-shared/` in line with the already-migrated layers (`core/`, `shared-composables/`, `shared-ui/`) so that the entire shared library surface has static typing, enabling safer refactors and better IDE support for admin module authors.

## Non-goals

- Do not migrate `admin/` feature modules (portal pages, views) — only the shared layer.
- Do not add new functionality or change runtime behaviour.

## Constraints

- Must follow the TypeScript migration rules documented in CLAUDE.md (Phase 1a–1c patterns).
- Node ≥22.6 required for parity-test execution (already satisfied by environment.yml).
- Must not introduce `any` where a typed alternative exists; prefer declared-interface + `@ts-expect-error` pattern for imports from not-yet-migrated directories.

## Known Context

- This is Phase 2, following Phase 1c (shared-ui/ migration, change-id: migrate-shared-ui-ts).
- `admin-shared/` has 1 composable (`.js`) and 4 Vue SFC components.
- No index barrel file detected yet — one may need to be created or audited.

## Open Questions

## Requested Delivery Date / Priority

Phase 2 — not yet scheduled; can proceed in parallel with resource-shared/ and wip-shared/ migrations.
