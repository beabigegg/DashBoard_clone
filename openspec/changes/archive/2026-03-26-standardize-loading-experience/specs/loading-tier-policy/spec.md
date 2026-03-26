## ADDED Requirements

### Requirement: Loading behavior SHALL be classified into three tiers
The system SHALL classify all loading states into exactly three tiers: page-level blocking, component-level inline, and block-level section loading.

#### Scenario: Tier classification during implementation
- **WHEN** a developer introduces or refactors a loading state
- **THEN** the loading state SHALL be assigned to one of the three tiers
- **THEN** the implementation SHALL follow the tier-specific component and behavior requirements

### Requirement: Page-level blocking loading SHALL use shared overlay components
Page-level blocking loading SHALL use `LoadingOverlay` with `tier="page"` and shared `LoadingSpinner`. Custom full-page spinner implementations MUST NOT be introduced.

#### Scenario: Initial query blocks primary page content
- **WHEN** a page performs an initial blocking query
- **THEN** it SHALL render `LoadingOverlay tier="page"` as the loading presentation
- **THEN** it SHALL NOT render a page-specific custom spinner class for the same state

### Requirement: Component-level loading SHALL use inline shared patterns
Component-level loading (button, trigger, inline indicator) SHALL use shared inline patterns based on `LoadingSpinner size="sm"` and disabled interaction while loading.

#### Scenario: Query button enters busy state
- **WHEN** a user triggers a query from an action button
- **THEN** the button SHALL enter a loading state with inline spinner and disabled interaction
- **THEN** the button text SHALL switch to loading copy (for example, 查詢中...)

### Requirement: Block-level loading SHALL use reusable section-level patterns
Block-level loading SHALL use reusable section-level patterns (`DataTable` loading state or shared block loading state component) instead of ad hoc placeholder-only implementations.

#### Scenario: Table section refreshes without full-page blocking
- **WHEN** a section table refreshes after filter or pagination changes
- **THEN** the section SHALL use the standardized block-level loading pattern
- **THEN** existing data presentation SHALL be visually consistent with shared loading behavior

### Requirement: Tiered loading SHALL respect reduced-motion settings
All loading tiers SHALL respect `prefers-reduced-motion` and disable non-essential animations.

#### Scenario: User prefers reduced motion
- **WHEN** the browser reports `prefers-reduced-motion: reduce`
- **THEN** spinner/skeleton/typing/pulse animations in loading states SHALL be disabled or reduced to a static state
