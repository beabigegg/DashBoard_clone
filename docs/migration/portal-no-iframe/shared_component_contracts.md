# Shared UI Component Contracts

## `PaginationControl`

File: `frontend/src/shared-ui/components/PaginationControl.vue`

- Props:
  - `page?: number` (legacy compatibility)
  - `modelValue?: number`
  - `totalPages: number`
  - `infoText?: string`
  - `visible?: boolean`
- Emits:
  - `update:modelValue(number)`
  - `change(number)`
  - `prev(number)`
  - `next(number)`
- Compatibility:
  - Supports legacy usage (`:page`, `@prev`, `@next`) for migration-safe replacement.

## `SectionCard`

File: `frontend/src/shared-ui/components/SectionCard.vue`

- Slots:
  - `header`
  - default body
  - `footer`
- Purpose:
  - Normalize page section container structure and spacing.

## `FilterToolbar`

File: `frontend/src/shared-ui/components/FilterToolbar.vue`

- Slots:
  - default filter controls
  - `actions`
- Purpose:
  - Shared filter layout shell with consistent spacing and action alignment.

## `StatusBadge`

File: `frontend/src/shared-ui/components/StatusBadge.vue`

- Props:
  - `tone: neutral | success | warning | danger`
  - `text: string`
- Purpose:
  - Replace repeated local badge/status color snippets.
