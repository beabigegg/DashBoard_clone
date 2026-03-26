## MODIFIED Requirements

### Requirement: ui-btn loading state
The system SHALL support `.ui-btn.is-loading` which disables pointer events, reduces opacity, and shows an inline `LoadingSpinner` inside the button with loading copy.

#### Scenario: Button loading state
- **WHEN** a button has class `is-loading`
- **THEN** pointer-events SHALL be `none`, opacity SHALL be reduced, and an inline spinner SHALL be visible
- **THEN** the button label SHALL switch to a loading-state label appropriate to the action (for example, 查詢中..., 匯出中..., 上傳中...)

#### Scenario: Loading state accessibility
- **WHEN** a button enters loading state
- **THEN** the button SHALL be non-interactive via `disabled` or equivalent behavior
- **THEN** assistive technology SHALL be able to detect the loading state from text or aria attributes

## ADDED Requirements

### Requirement: Loading button behavior SHALL be reusable across pages
The system SHALL provide a reusable loading-button implementation pattern for query/export/upload actions to avoid page-specific busy-state divergence.

#### Scenario: Cross-page consistency for action buttons
- **WHEN** query/export/upload buttons are implemented across different pages
- **THEN** they SHALL reuse the shared loading-button pattern
- **THEN** they SHALL present consistent spinner placement, disabled behavior, and loading label transitions
