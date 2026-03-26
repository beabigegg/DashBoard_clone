## ADDED Requirements

### Requirement: useFilterOrchestrator composable
The system SHALL provide a `useFilterOrchestrator` composable at `shared-composables/useFilterOrchestrator.js` that accepts a configuration object describing fields, dependencies, pagination rules, and URL sync settings.

#### Scenario: Configuration-driven initialization
- **WHEN** a page calls `useFilterOrchestrator({ fields, dependencies, pagination, urlSync })`
- **THEN** it SHALL return reactive `committed`, `draft`, `options`, `pagination` refs plus `applyDraft()`, `updateField()`, `resetAll()` methods

### Requirement: Draft-Apply mode support
Fields configured with `trigger: 'draft-apply'` SHALL accumulate changes in `draft` without triggering data fetch. Only when `applyDraft()` is called SHALL `committed` be updated and data fetch triggered.

#### Scenario: Draft changes do not trigger fetch
- **WHEN** a draft field value changes
- **THEN** `committed` SHALL NOT change and no fetch SHALL be triggered

#### Scenario: Apply draft commits and fetches
- **WHEN** `applyDraft()` is called
- **THEN** all draft values SHALL be copied to `committed` and `onFetch` callback SHALL be invoked

### Requirement: Immediate mode support
Fields configured with `trigger: 'immediate'` SHALL update `committed` immediately on change and trigger data fetch.

#### Scenario: Immediate field triggers fetch
- **WHEN** an immediate field value changes via `updateField()`
- **THEN** `committed` SHALL update immediately and `onFetch` callback SHALL be invoked

### Requirement: Two-phase query mode support
The composable SHALL support two-phase query via `onPrimaryQuery` (executes server query, returns queryId) and `onViewRefresh` (reads cached results with supplementary filters).

#### Scenario: Primary query followed by supplementary filter
- **WHEN** primary filter changes trigger `onPrimaryQuery`
- **THEN** supplementary filter fields SHALL become enabled after primary query completes
- **WHEN** a supplementary filter changes
- **THEN** `onViewRefresh` SHALL be invoked (not `onPrimaryQuery`)

### Requirement: Mutual exclusive toggle mode support
The composable SHALL support mutual exclusive fields where selecting one clears the others, configured via dependency `action: 'clear'` with mutual references.

#### Scenario: Selecting one toggle clears others
- **WHEN** field A is set in a mutual-exclusive group
- **THEN** fields B and C in the same group SHALL be cleared and page SHALL reset to 1

### Requirement: Cross-field dependency handling
The `dependencies` array SHALL define reactive relationships. Supported actions: `reload-options` (re-fetch options for target fields), `clear` (reset target fields to initial), `reset` (reset to specific value).

#### Scenario: Upstream change reloads downstream options
- **WHEN** `holdType` changes and a dependency `{ when: 'holdType', then: ['reason'], action: 'reload-options' }` exists
- **THEN** the options for `reason` SHALL be reloaded

#### Scenario: Upstream change clears downstream values
- **WHEN** `holdType` changes and a dependency `{ when: 'holdType', then: ['matrixFilter'], action: 'clear' }` exists
- **THEN** `matrixFilter` value SHALL be reset to its initial value

### Requirement: Debounced option reloading
Dependencies MAY specify a `debounce` value in milliseconds. When present, the action SHALL be debounced by that duration.

#### Scenario: Draft field option reload debounced at 120ms
- **WHEN** a draft field changes and dependency has `debounce: 120`
- **THEN** the reload-options action SHALL wait 120ms before executing, cancelling prior pending reloads

### Requirement: Pagination auto-reset
The composable SHALL reset pagination to page 1 when any filter value in `pagination.resetOn` changes. `'*'` means all fields.

#### Scenario: Filter change resets to page 1
- **WHEN** any committed filter value changes and `pagination.resetOn` is `['*']`
- **THEN** `pagination.page` SHALL be set to 1

### Requirement: URL sync
When `urlSync.enabled` is `true`, the composable SHALL serialize committed filter values to URL query parameters and restore them on page load.

#### Scenario: Bookmark URL restores filter state
- **WHEN** a user bookmarks a URL with filter query parameters and revisits it
- **THEN** all committed filter values SHALL be restored from the URL

### Requirement: useRequestGuard composable
The system SHALL provide `useRequestGuard` at `shared-composables/useRequestGuard.js` exposing `nextRequestId()` and `isStaleRequest(id)` for race condition prevention.

#### Scenario: Stale request detection
- **WHEN** request A (id=1) is in flight and request B (id=2) starts
- **THEN** `isStaleRequest(1)` SHALL return `true` and `isStaleRequest(2)` SHALL return `false`

### Requirement: useUrlSync composable
The system SHALL provide `useUrlSync` at `shared-composables/useUrlSync.js` encapsulating URL query parameter serialization/deserialization logic.

#### Scenario: Serialize filter state to URL
- **WHEN** `syncToUrl(state)` is called
- **THEN** the browser URL SHALL update with the serialized filter parameters without page reload
