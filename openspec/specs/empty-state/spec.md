## ADDED Requirements

### Requirement: EmptyState component
The system SHALL provide an `EmptyState` component at `shared-ui/components/EmptyState.vue` with a `type` prop that selects the display message.

#### Scenario: No data state
- **WHEN** `EmptyState` is rendered with `type="no-data"`
- **THEN** it SHALL display "目前沒有資料"

#### Scenario: Filter empty state
- **WHEN** `EmptyState` is rendered with `type="filter-empty"`
- **THEN** it SHALL display "找不到符合條件的資料"

#### Scenario: Error state
- **WHEN** `EmptyState` is rendered with `type="error"`
- **THEN** it SHALL display "資料載入失敗，請稍後再試"

#### Scenario: Loading state
- **WHEN** `EmptyState` is rendered with `type="loading"`
- **THEN** it SHALL display "資料載入中..."

### Requirement: EmptyState visual consistency
The `EmptyState` component SHALL render centered text with consistent padding, font-size, and muted color across all types. It SHALL accept an optional `icon` slot for custom icons.

#### Scenario: Centered display
- **WHEN** `EmptyState` renders in any type
- **THEN** the message SHALL be horizontally and vertically centered within its container with muted text color

### Requirement: All pages use EmptyState component
All existing empty state messages ("無資料", "No data", "無符合項目", etc.) across all pages SHALL be replaced with the `EmptyState` component using the appropriate `type` prop.

#### Scenario: Unified empty state across pages
- **WHEN** a page has no data to display after a filter or initial load
- **THEN** it SHALL render `EmptyState` with the correct `type` instead of inline text

### Requirement: EmptyState SHALL support illustration and action slots

#### Scenario: Illustration slot
- **WHEN** `EmptyState` has a `#illustration` slot
- **THEN** it SHALL render the slot content above the message text
- **WHEN** no `#illustration` slot is provided
- **THEN** no illustration area SHALL be rendered (current behavior preserved)

#### Scenario: Action slot
- **WHEN** `EmptyState` has a `#action` slot
- **THEN** it SHALL render the slot content below the message text with `margin-top: 16px`
- **THEN** the action area SHALL be centered

#### Scenario: Backward compatibility
- **WHEN** `EmptyState` is used without new slots
- **THEN** it SHALL render identically to current behavior (message text only based on `type` prop)
