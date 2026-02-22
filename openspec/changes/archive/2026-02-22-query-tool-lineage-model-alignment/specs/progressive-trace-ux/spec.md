## MODIFIED Requirements

### Requirement: query-tool lineage tab SHALL load on-demand
The query-tool lineage experience SHALL keep progressive loading behavior while supporting forward and reverse tracing semantics with independent caches.

#### Scenario: Forward resolve auto-fires lineage progressively
- **WHEN** forward seed resolution completes with N lots
- **THEN** lineage requests SHALL auto-fire with concurrency control
- **THEN** the tree SHALL progressively render as responses arrive

#### Scenario: Reverse resolve supports serial, GD work-order, and GD lot-id modes
- **WHEN** reverse tab resolves seeds using `serial_number`, `gd_work_order`, or `gd_lot_id`
- **THEN** lineage SHALL render upstream graph from resolved roots
- **THEN** reverse tab behavior SHALL not depend on forward tab state

#### Scenario: Cache isolation per tab context
- **WHEN** lineage data is fetched in forward tab
- **THEN** forward cache SHALL be reusable within forward context
- **THEN** reverse tab lineage cache SHALL be isolated from forward cache state

#### Scenario: Tree interaction does not mutate graph scope
- **WHEN** user clicks nodes to inspect details
- **THEN** detail panel scope SHALL update immediately
- **THEN** lineage graph visibility SHALL remain unchanged unless a new resolve is executed
