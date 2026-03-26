## ADDED Requirements

### Requirement: Lineage tree SHALL limit initial expansion depth
The LineageTreeChart SHALL NOT fully expand all nodes on initial render to improve performance with large trees.

#### Scenario: Default expansion depth
- **WHEN** a lineage tree renders with data
- **THEN** `initialTreeDepth` SHALL be set to 2 (root + 2 levels visible)

#### Scenario: Expand all button
- **WHEN** the user clicks the "全部展開" button in the tree toolbar
- **THEN** all tree nodes SHALL expand to show the complete hierarchy

#### Scenario: Collapse all button
- **WHEN** the user clicks the "全部收合" button in the tree toolbar
- **THEN** all tree nodes except root SHALL collapse

### Requirement: Lineage tree SHALL support zoom interaction
The LineageTreeChart SHALL allow users to zoom in/out in addition to panning, to facilitate navigation of large trees.

#### Scenario: Scroll wheel zoom
- **WHEN** a user scrolls the mouse wheel over the tree chart
- **THEN** the chart SHALL zoom in or out centered on the cursor position

#### Scenario: Reset view button
- **WHEN** the user clicks the "重置視圖" button
- **THEN** the chart SHALL restore to the default zoom level and position

#### Scenario: ECharts roam configuration
- **WHEN** the tree chart option is configured
- **THEN** `roam` SHALL be set to `true` (enabling both pan and zoom)

### Requirement: Relation table SHALL support pagination
The lineage relation table SHALL use paginated display instead of truncating at a fixed row count.

#### Scenario: Pagination control
- **WHEN** the relation table has more than 50 rows
- **THEN** a `PaginationControl` component SHALL be rendered below the table
- **THEN** the default page size SHALL be 50

#### Scenario: Page navigation
- **WHEN** the user navigates to page 2 of the relation table
- **THEN** rows 51-100 SHALL be displayed

### Requirement: PNG export SHALL show loading feedback
The tree PNG export operation SHALL display a loading indicator while the export is being generated.

#### Scenario: Export loading state
- **WHEN** the user clicks the PNG export button
- **THEN** a `LoadingOverlay` SHALL be displayed until the export completes

#### Scenario: Export pixel ratio
- **WHEN** the PNG export is generated
- **THEN** the `devicePixelRatio` SHALL be capped at 2 to balance quality and performance
