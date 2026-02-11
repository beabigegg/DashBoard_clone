# Shared Composables Contracts

## `useAutoRefresh`

File: `frontend/src/shared-composables/useAutoRefresh.js`

- Current behavior wraps existing `wip-shared` implementation.
- Purpose: single import path for all page modules before deeper implementation merge.

## `useAutocomplete`

File: `frontend/src/shared-composables/useAutocomplete.js`

- Current behavior wraps existing `wip-shared` implementation.
- Purpose: single import path to normalize field/autocomplete interactions.

## `usePaginationState`

File: `frontend/src/shared-composables/usePaginationState.js`

- State: `page`, `perPage`, `total`, `totalPages`
- Derived: `hasPrev`, `hasNext`
- Methods: `setFromPayload`, `reset`

## `useQueryState`

File: `frontend/src/shared-composables/useQueryState.js`

- `readQueryState(keys)`
- `writeQueryState(nextState)`
- Purpose: unify URL query read/write semantics across pages.
