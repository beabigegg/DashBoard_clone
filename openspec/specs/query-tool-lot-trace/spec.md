## ADDED Requirements

### Requirement: Query-tool page SHALL use tab-based layout separating LOT tracing from equipment queries
The query-tool page SHALL present two top-level tabs: "LOT 追蹤" and "設備查詢", each with independent state and UI.

#### Scenario: Tab switching preserves state
- **WHEN** the user switches from LOT tab to Equipment tab and back
- **THEN** the LOT tab SHALL retain its resolved lots, lineage tree state, and selected lot detail
- **THEN** the Equipment tab SHALL retain its query results independently

#### Scenario: URL state reflects active tab
- **WHEN** the user is on a specific tab
- **THEN** the URL SHALL include a `tab` parameter (e.g., `?tab=lot` or `?tab=equipment`)
- **THEN** reloading the page SHALL restore the active tab

### Requirement: QueryBar SHALL resolve LOT/Serial/WorkOrder inputs
The query bar SHALL accept multi-value input (newline or comma-separated) with input type selection and resolve via `POST /api/query-tool/resolve`.

#### Scenario: Successful LOT resolution
- **WHEN** the user enters lot IDs and clicks resolve
- **THEN** the system SHALL call `POST /api/query-tool/resolve` with `input_type` and `values`
- **THEN** resolved lots SHALL appear as root nodes in the lineage tree
- **THEN** not-found values SHALL be displayed as warnings below the tree

#### Scenario: Work order expansion
- **WHEN** the user enters work order IDs (max 10)
- **THEN** each work order MAY expand to 100+ lots
- **THEN** all expanded lots SHALL appear as root nodes in the lineage tree

#### Scenario: Input validation
- **WHEN** the user submits empty input or exceeds limits (50 lot IDs, 50 serial numbers, 10 work orders)
- **THEN** the system SHALL display a validation error without making an API call

### Requirement: LineageTree SHALL display as a decomposition tree with progressive growth animation
After resolve completes, the lineage tree SHALL auto-fire lineage API calls for each resolved lot with concurrency control, rendering an animated tree that grows as results arrive.

#### Scenario: Auto-fire lineage after resolve
- **WHEN** lot resolution completes with N resolved lots
- **THEN** the system SHALL automatically call `POST /api/trace/lineage` for each lot
- **THEN** concurrent lineage requests SHALL be limited to 3 at a time
- **THEN** the lineage tree SHALL render root nodes immediately (resolved lots)

#### Scenario: Progressive tree growth animation
- **WHEN** a lineage API response returns for a lot
- **THEN** ancestor nodes SHALL animate into the tree (slide-in + fade, staggered 30-50ms per sibling)
- **THEN** the animation SHALL give the visual impression of a tree "growing" its branches

#### Scenario: Tree node expand/collapse
- **WHEN** the user clicks a tree node with children (ancestors)
- **THEN** children SHALL toggle between expanded and collapsed state
- **THEN** expand/collapse SHALL be a client-side operation (no additional API call)

#### Scenario: Expand-all and collapse-all
- **WHEN** the user clicks "全部展開"
- **THEN** all tree nodes at all levels SHALL expand with staggered animation
- **WHEN** the user clicks "收合"
- **THEN** all tree nodes SHALL collapse to show only root nodes

#### Scenario: Merge relationships visually distinct
- **WHEN** the lineage data includes merge relationships
- **THEN** merge nodes SHALL display a distinct icon and/or color to differentiate from direct ancestor relationships

#### Scenario: Leaf nodes without expand affordance
- **WHEN** a tree node has no ancestors (leaf/terminal node)
- **THEN** it SHALL NOT display an expand button or clickable expand area

#### Scenario: Lineage cache prevents duplicate fetches
- **WHEN** lineage data has already been fetched for a lot
- **THEN** subsequent interactions SHALL use cached data without re-fetching
- **WHEN** a new resolve query is executed
- **THEN** the lineage cache SHALL be cleared

### Requirement: Left-right master-detail layout SHALL show tree and LOT detail side by side
The LOT tracing tab SHALL use a left-right split layout with the lineage tree on the left and LOT detail on the right.

#### Scenario: LOT selection from tree
- **WHEN** the user clicks any node in the lineage tree (root lot or ancestor)
- **THEN** the right panel SHALL load detail for that node's container ID
- **THEN** the selected node SHALL be visually highlighted in the tree

#### Scenario: Right panel sub-tabs
- **WHEN** a LOT is selected
- **THEN** the right panel SHALL display sub-tabs: 歷程 (History), 物料 (Materials), 退貨 (Rejects), Hold, Split, Job
- **THEN** each sub-tab SHALL load data on-demand when activated (not pre-fetched)

#### Scenario: Responsive behavior
- **WHEN** the viewport width is below 1024px
- **THEN** the layout SHALL stack vertically (tree above, detail below)

### Requirement: LOT History sub-tab SHALL display production history with workcenter filter
The History sub-tab SHALL show production history data from `GET /api/query-tool/lot-history` with workcenter group filtering.

#### Scenario: History table display
- **WHEN** the user selects the History sub-tab for a LOT
- **THEN** the system SHALL call `GET /api/query-tool/lot-history?container_id=X`
- **THEN** results SHALL display in a table with sticky headers and horizontal scroll

#### Scenario: Workcenter group filter
- **WHEN** the user selects workcenter groups from the filter dropdown
- **THEN** the history query SHALL include the selected groups as filter parameters
- **THEN** the history table SHALL refresh with filtered results

### Requirement: LOT Production Timeline SHALL visualize station progression over time
The History sub-tab SHALL include a timeline visualization showing the lot's journey through production stations.

#### Scenario: Timeline rendering
- **WHEN** lot history data is loaded
- **THEN** a horizontal Gantt-style timeline SHALL render with time on the X-axis
- **THEN** each workcenter/station SHALL appear as a track with a colored bar from track-in to track-out time

#### Scenario: Workcenter filter affects timeline
- **WHEN** the user filters by workcenter groups
- **THEN** the timeline SHALL show only stations matching the selected groups
- **THEN** filtered-out stations SHALL be hidden (not grayed out)

#### Scenario: Timeline event markers
- **WHEN** hold events or material consumption events exist within the timeline range
- **THEN** they SHALL be displayed as markers on the timeline with tooltip details on hover

### Requirement: LOT Association sub-tabs SHALL load data on-demand
Each association sub-tab (Materials, Rejects, Holds, Splits, Jobs) SHALL fetch data independently when activated.

#### Scenario: Association data loading
- **WHEN** the user activates a sub-tab (e.g., Materials)
- **THEN** the system SHALL call `GET /api/query-tool/lot-associations?container_id=X&type=materials`
- **THEN** results SHALL display in a table with dynamic columns

#### Scenario: Sub-tab data caching within session
- **WHEN** the user switches between sub-tabs for the same LOT
- **THEN** previously loaded sub-tab data SHALL be preserved (not re-fetched)
- **WHEN** the user selects a different LOT
- **THEN** all sub-tab caches SHALL be cleared

### Requirement: Each sub-tab SHALL support independent CSV export
Every detail sub-tab SHALL have its own export button.

#### Scenario: Per-tab export
- **WHEN** the user clicks export on the Materials sub-tab
- **THEN** the system SHALL call `POST /api/query-tool/export-csv` with `export_type: "lot_materials"` and the current container_id
- **THEN** a CSV file SHALL download with the appropriate filename

#### Scenario: Export disabled when no data
- **WHEN** a sub-tab has no data loaded or the data is empty
- **THEN** the export button SHALL be disabled

### Requirement: Legacy dead code SHALL be removed
The legacy `frontend/src/query-tool/main.js` (448L vanilla JS) and `frontend/src/query-tool/style.css` SHALL be deleted.

#### Scenario: Dead code removal
- **WHEN** the rewrite is complete
- **THEN** `frontend/src/query-tool/main.js` SHALL contain only the Vite entry point (createApp + mount)
- **THEN** `frontend/src/query-tool/style.css` SHALL be deleted (all styling via Tailwind)
