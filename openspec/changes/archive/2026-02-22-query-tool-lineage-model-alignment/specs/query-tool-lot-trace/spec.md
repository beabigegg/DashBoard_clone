## MODIFIED Requirements

### Requirement: Query-tool page SHALL use tab-based layout separating LOT tracing from equipment queries
The query-tool page SHALL present three top-level tabs with independent state: `批次追蹤(正向)`, `流水批反查(反向)`, and `設備生產批次追蹤`.

#### Scenario: Tab switching preserves independent state
- **WHEN** the user switches between forward, reverse, and equipment tabs
- **THEN** each tab SHALL retain its own input values, resolved seeds, selected nodes, and detail sub-tab state
- **THEN** switching tabs SHALL NOT clear another tab's query context

#### Scenario: URL state reflects active tab and tab-local inputs
- **WHEN** the user is on a specific tab
- **THEN** the URL SHALL include `tab` and corresponding tab-local query parameters
- **THEN** reloading the page SHALL restore the active tab and its tab-local state

### Requirement: QueryBar SHALL resolve LOT/Serial/WorkOrder inputs
The query bar SHALL support profile-specific input types. Forward tracing SHALL support wafer/lot/work-order inputs, and reverse tracing SHALL support serial, GD work-order, and GD lot-id inputs.

#### Scenario: Forward query supports wafer-lot seeds
- **WHEN** the user selects `wafer_lot` in forward tab and submits values
- **THEN** the system SHALL call resolve API with `input_type=wafer_lot`
- **THEN** resolved lots under the wafer origin SHALL appear as forward tree roots

#### Scenario: Reverse query supports GD work-order seeds
- **WHEN** the user selects `gd_work_order` in reverse tab and submits `GD%` work orders
- **THEN** the system SHALL call resolve API with `input_type=gd_work_order`
- **THEN** resolved GD lots SHALL appear as reverse tree roots

#### Scenario: Reverse query supports GD lot-id seeds
- **WHEN** the user selects `gd_lot_id` in reverse tab and submits GD lot IDs
- **THEN** the system SHALL call resolve API with `input_type=gd_lot_id`
- **THEN** resolved GD lot roots SHALL be used for reverse lineage expansion

#### Scenario: Invalid GD work-order input is rejected
- **WHEN** reverse tab input type is `gd_work_order` and a value does not match `GD%`
- **THEN** the system SHALL return validation error without issuing lineage query
- **THEN** the UI SHALL keep user input and display actionable error text

#### Scenario: Invalid GD lot-id input is rejected
- **WHEN** reverse tab input type is `gd_lot_id` and a value does not match GD lot rules
- **THEN** the system SHALL return validation error without issuing lineage query
- **THEN** invalid values SHALL be reported in the UI without clearing user input

### Requirement: LineageTree SHALL display as a decomposition tree with progressive growth animation
The lineage tree SHALL render semantic node/edge relationships and SHALL preserve progressive loading behavior.

#### Scenario: GC is optional and wafer linkage remains visible
- **WHEN** a GA lot has no GC node in its upstream chain
- **THEN** the tree SHALL still render a direct `WAFER -> GA` relationship
- **THEN** this SHALL NOT be treated as a broken lineage

#### Scenario: GD rework branch is explicitly rendered
- **WHEN** lineage includes GD rework data
- **THEN** the tree SHALL render `source lot -> GD lot -> new serial/lot` using GD-specific node/edge style
- **THEN** users SHALL be able to distinguish GD rework edges from split/merge edges

#### Scenario: Auto-fire lineage after forward resolve
- **WHEN** forward lot resolution completes with N resolved lots
- **THEN** lineage SHALL be fetched automatically with concurrency-limited requests
- **THEN** the tree SHALL progressively grow as lineage responses arrive

#### Scenario: Node click only scopes detail panel
- **WHEN** the user clicks one or more nodes in the tree
- **THEN** only the detail panel query scope SHALL change
- **THEN** the tree structure and node visibility SHALL remain unchanged
