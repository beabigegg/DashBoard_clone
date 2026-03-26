## ADDED Requirements

### Requirement: LoadingOverlay component with page tier
The system SHALL provide a `LoadingOverlay` component at `shared-ui/components/LoadingOverlay.vue`. When `tier="page"`, it SHALL render a full-viewport overlay with `var(--overlay-bg)` background and a large (lg) spinner centered.

#### Scenario: Page-level loading on initial load
- **WHEN** `LoadingOverlay` is rendered with `tier="page"`
- **THEN** it SHALL cover the entire parent container with a semi-transparent white overlay and display a centered large spinner

### Requirement: LoadingOverlay component with section tier
When `tier="section"`, the overlay SHALL cover only its parent container (via `position: absolute` within a `position: relative` parent) with the same background and a medium (md) spinner.

#### Scenario: Section-level loading on data reload
- **WHEN** `LoadingOverlay` is rendered with `tier="section"` inside a relatively-positioned parent
- **THEN** it SHALL cover only that parent section with overlay and a medium spinner

### Requirement: LoadingSpinner component
The system SHALL provide a `LoadingSpinner` component at `shared-ui/components/LoadingSpinner.vue` with `size` prop accepting `sm` (14px), `md` (24px), `lg` (42px).

#### Scenario: Spinner sizes render correctly
- **WHEN** `LoadingSpinner` is rendered with `size="sm"`
- **THEN** the spinner SHALL be 14px diameter with proportional border-width
- **WHEN** `LoadingSpinner` is rendered with `size="lg"`
- **THEN** the spinner SHALL be 42px diameter with proportional border-width

### Requirement: LoadingSpinner used inline in buttons
The `LoadingSpinner` with `size="sm"` SHALL be usable inside `.ui-btn.is-loading` to provide inline loading feedback.

#### Scenario: Inline spinner in button
- **WHEN** a `.ui-btn.is-loading` button renders
- **THEN** a `LoadingSpinner size="sm"` SHALL appear adjacent to the button text

### Requirement: Replace all existing inline loading implementations
All page-specific loading overlays and spinner CSS (in `wip-shared/styles.css`, `resource-shared/styles.css`, individual page `style.css` files) SHALL be replaced by `LoadingOverlay` and `LoadingSpinner` components.

#### Scenario: No duplicate loading CSS remains
- **WHEN** inspecting `wip-shared/styles.css` and `resource-shared/styles.css`
- **THEN** no `.loading-overlay`, `.spinner`, or equivalent custom loading CSS definitions SHALL remain
