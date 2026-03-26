## ADDED Requirements

### Requirement: All pages migrate to unified components
Every page (hold-overview, hold-detail, hold-history, wip-overview, wip-detail, reject-history, yield-alert-center, resource-status, resource-history, mid-section-defect) SHALL use `LoadingOverlay`, `LoadingSpinner`, `EmptyState`, and `MultiSelect` from `shared-ui` instead of page-specific implementations.

#### Scenario: hold-overview uses shared components
- **WHEN** hold-overview page renders loading, empty, or multiselect states
- **THEN** it SHALL use `LoadingOverlay`, `EmptyState`, and `MultiSelect` from `shared-ui`

#### Scenario: All pages import from shared-ui
- **WHEN** inspecting imports across all page directories
- **THEN** no page SHALL import loading, empty state, or multiselect from local or feature-shared directories

### Requirement: All pages migrate to ui-btn classes
Every page SHALL replace `.btn-primary`, `.btn-secondary`, `.btn` with `.ui-btn`, `.ui-btn--primary`, `.ui-btn--ghost`, `.ui-btn--sm` as appropriate.

#### Scenario: No legacy button classes in Vue files
- **WHEN** running grep for `.btn-primary` or `.btn-secondary` across all `.vue` files
- **THEN** zero matches SHALL be returned

### Requirement: All pages migrate to useFilterOrchestrator
Every page with filter logic SHALL replace inline filter state management with `useFilterOrchestrator` configured for its specific filter mode and cross-dependencies.

#### Scenario: hold-overview filter orchestrator config
- **WHEN** hold-overview initializes filters
- **THEN** it SHALL use `useFilterOrchestrator` with Draft→Apply mode for panel fields, immediate mode for HoldType bar, and dependencies: HoldType→Reason reload + Matrix clear

#### Scenario: hold-history two-phase config
- **WHEN** hold-history initializes filters
- **THEN** it SHALL use `useFilterOrchestrator` with two-phase mode: Date Apply triggers primary query, supplementary filters (HoldType, RecordType, Reason, Duration) read from cache

#### Scenario: resource-status cascading config
- **WHEN** resource-status initializes filters
- **THEN** it SHALL use `useFilterOrchestrator` with cascading immediate mode: Group/Flags→Family prune→Machine prune

### Requirement: All pages use motion tokens
Every page SHALL reference `var(--motion-*)` tokens instead of hardcoded transition durations and `var(--hover-lift)` instead of hardcoded translateY values.

#### Scenario: No hardcoded transitions after migration
- **WHEN** inspecting all page CSS and style blocks
- **THEN** all transition durations SHALL use `var(--motion-fast)`, `var(--motion-normal)`, or `var(--motion-slow)`

### Requirement: All pages use search trigger animation
Every page with a "套用" or "查詢" button SHALL implement the unified search trigger animation (button spinner + table dimming + fade-in).

#### Scenario: Consistent search feedback across pages
- **WHEN** user clicks "套用" on any page
- **THEN** the button SHALL show spinner, the table SHALL dim, and data SHALL fade in on completion

### Requirement: Feature style cleanup
After migration, `wip-shared/styles.css` and `resource-shared/styles.css` SHALL have redundant loading/spinner/empty-state/error-banner CSS definitions removed. Each page's `style.css` SHALL have legacy button classes, hardcoded transitions, and inconsistent hover effects removed.

#### Scenario: wip-shared styles cleaned
- **WHEN** inspecting `wip-shared/styles.css`
- **THEN** no `.loading-overlay`, `.spinner`, `.error-banner` definitions that duplicate shared-ui components SHALL remain

### Requirement: CSS inventory contract updated
`contract/css_inventory.md` SHALL be updated to reflect new CSS files added and any CSS files removed or significantly modified.

#### Scenario: CSS inventory reflects changes
- **WHEN** inspecting `contract/css_inventory.md`
- **THEN** it SHALL list all new shared-ui component styles and reflect removal of duplicate definitions from feature styles
