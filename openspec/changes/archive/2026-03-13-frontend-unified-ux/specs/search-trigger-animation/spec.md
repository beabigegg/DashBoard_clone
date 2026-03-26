## ADDED Requirements

### Requirement: Button loading feedback on search trigger
When a user clicks "套用" or "查詢" button, the button SHALL enter `.is-loading` state showing an inline spinner and disabling further clicks until the fetch completes.

#### Scenario: Apply button shows spinner
- **WHEN** user clicks the "套用" button
- **THEN** the button SHALL show an inline `LoadingSpinner size="sm"` and disable pointer events
- **WHEN** the data fetch completes
- **THEN** the button SHALL return to its normal state

### Requirement: Table dimming during fetch
When a data fetch is triggered, the table/content area SHALL apply `.ui-table-wrap.is-loading` which reduces opacity to 0.5 and disables pointer events, using `transition: opacity var(--motion-normal) var(--motion-ease)`.

#### Scenario: Table dims during loading
- **WHEN** a filter apply triggers a data fetch
- **THEN** the table wrapper SHALL have `opacity: 0.5` and `pointer-events: none`
- **WHEN** the fetch completes
- **THEN** opacity SHALL animate back to 1 and pointer-events SHALL be restored

### Requirement: Fade-in on data load completion
When data loading completes, the content area SHALL fade in with `opacity: 0.5→1` and `translateY: 4px→0` over `var(--motion-normal)`.

#### Scenario: Content fades in after load
- **WHEN** new data renders after a fetch
- **THEN** the content SHALL animate from `opacity: 0.5; translateY(4px)` to `opacity: 1; translateY(0)` over 200ms
