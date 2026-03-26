## MODIFIED Requirements

### Requirement: LoadingOverlay component with page tier
The system SHALL provide a `LoadingOverlay` component at `shared-ui/components/LoadingOverlay.vue`. When `tier="page"`, it SHALL render a full-viewport overlay with `var(--overlay-bg)` background and a large (lg) spinner centered, and SHALL be the required implementation for page-level blocking loading states.

#### Scenario: Page-level loading on initial load
- **WHEN** `LoadingOverlay` is rendered with `tier="page"`
- **THEN** it SHALL cover the entire parent container with a semi-transparent overlay and display a centered large spinner
- **THEN** the page SHALL NOT render a parallel custom full-page spinner implementation

### Requirement: LoadingSpinner component
The system SHALL provide a `LoadingSpinner` component at `shared-ui/components/LoadingSpinner.vue` with `size` prop accepting `sm` (14px), `md` (24px), `lg` (42px), and SHALL use the shared spinner animation baseline for loading rotation.

#### Scenario: Spinner sizes render correctly
- **WHEN** `LoadingSpinner` is rendered with `size="sm"`
- **THEN** the spinner SHALL be 14px diameter with proportional border-width
- **WHEN** `LoadingSpinner` is rendered with `size="lg"`
- **THEN** the spinner SHALL be 42px diameter with proportional border-width

#### Scenario: Shared spinner animation baseline
- **WHEN** `LoadingSpinner` is rendered in any context
- **THEN** it SHALL use the shared rotation animation baseline rather than page-specific keyframes

### Requirement: Replace all existing inline loading implementations
Page-level custom loading overlays and page-specific full-screen spinner CSS SHALL be replaced by `LoadingOverlay` and `LoadingSpinner` components. Component-level and block-level loading MAY keep contextual UI, but MUST follow shared tier patterns.

#### Scenario: No duplicate page-level loading CSS remains
- **WHEN** inspecting page and shared CSS for full-screen loading implementations
- **THEN** no custom full-page `.loading-overlay` or equivalent spinner implementation SHALL remain outside shared loading components
- **THEN** contextual component/block loading implementations SHALL remain allowed only when they follow tier policy requirements
