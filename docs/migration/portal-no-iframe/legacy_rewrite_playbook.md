# Legacy Rewrite Playbook (Batch-2)

## Target Pages

This playbook governs rewrite execution for the remaining three legacy pages:

- `/job-query`
- `/excel-query`
- `/query-tool`

Rewrite order follows `legacy_rewrite_priority_matrix.md`.

## Canonical Steps

1. Preserve route and API contracts first.
2. Move page state and API calls into composables (`use<Page>Data`).
3. Replace page-local repeated blocks with shared UI components where possible.
4. Keep Tailwind token alignment for new/changed UI.
5. Validate with per-page smoke checklist before/after switch.

## Required Acceptance (Per Page)

- Route reachable and functional without shell wrapper.
- Core query workflow succeeds and returns expected result sections.
- Export path remains usable (where applicable).
- No new unhandled runtime error on the primary path.
- Checklist IDs pass:
  - `/job-query`: `JOB-SMOKE-01`~`JOB-SMOKE-06`
  - `/excel-query`: `EXCEL-SMOKE-01`~`EXCEL-SMOKE-06`
  - `/query-tool`: `QTOOL-SMOKE-01`~`QTOOL-SMOKE-06`

Checklist source:

- `docs/migration/portal-no-iframe/legacy_rewrite_smoke_checklists.md`

## Shared Guardrails

- Do not change backend API signatures in rewrite phase.
- Keep direct-link behavior and query semantics stable.
- If parity fails, rollback to previous stable page artifact before continuing.
