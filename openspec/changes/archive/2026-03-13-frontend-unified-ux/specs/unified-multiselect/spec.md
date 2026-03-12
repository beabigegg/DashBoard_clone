## ADDED Requirements

### Requirement: Unified MultiSelect component
The system SHALL provide a single `MultiSelect` component at `shared-ui/components/MultiSelect.vue`, merging functionality from `resource-shared/components/MultiSelect.vue` and `mid-section-defect/components/MultiSelect.vue`.

#### Scenario: Component location
- **WHEN** any page imports MultiSelect
- **THEN** the import path SHALL be from `shared-ui/components/MultiSelect.vue`

### Requirement: Searchable by default
The `MultiSelect` SHALL have a `searchable` prop defaulting to `true`. When enabled, a search input SHALL filter options by matching both `label` and `value` fields.

#### Scenario: Search filters by label and value
- **WHEN** user types "ABC" in the search input
- **THEN** options whose `label` OR `value` contains "ABC" (case-insensitive) SHALL be shown

### Requirement: Select-all respects search filter
The `MultiSelect` SHALL have a `selectAllScope` prop with values `'visible'` (default) or `'all'`. When `'visible'`, the select-all checkbox SHALL toggle only the currently visible (filtered) options.

#### Scenario: Select all with visible scope
- **WHEN** user searches "X" filtering to 3 options, then clicks select-all
- **THEN** only those 3 visible options SHALL be selected, not all options

#### Scenario: Select all with all scope
- **WHEN** `selectAllScope` is `'all'` and user clicks select-all
- **THEN** all options SHALL be selected regardless of search filter

### Requirement: requestAnimationFrame focus management
The `MultiSelect` SHALL use `requestAnimationFrame` when managing focus on the search input after dropdown open, ensuring reliable focus across browsers.

#### Scenario: Focus on dropdown open
- **WHEN** the MultiSelect dropdown opens
- **THEN** the search input SHALL receive focus via `requestAnimationFrame`

### Requirement: Delete duplicate MultiSelect
The file `mid-section-defect/components/MultiSelect.vue` SHALL be deleted. All imports in `mid-section-defect` pages SHALL be updated to use `shared-ui/components/MultiSelect.vue`.

#### Scenario: No duplicate MultiSelect remains
- **WHEN** running `grep -r "from.*mid-section-defect.*MultiSelect" frontend/src/`
- **THEN** zero matches SHALL be returned

### Requirement: Resource-shared MultiSelect replaced
All imports of `MultiSelect` from `resource-shared/components/` SHALL be updated to import from `shared-ui/components/MultiSelect.vue`. The `resource-shared` version MAY be kept as a re-export or deleted.

#### Scenario: No direct resource-shared MultiSelect import
- **WHEN** running `grep -r "from.*resource-shared.*MultiSelect" frontend/src/ --include="*.vue"`
- **THEN** zero matches SHALL be returned (or only a re-export file)
