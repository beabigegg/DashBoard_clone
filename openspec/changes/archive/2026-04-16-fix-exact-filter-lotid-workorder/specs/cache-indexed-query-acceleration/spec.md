## MODIFIED Requirements

### Requirement: Query Paths SHALL Use Indexed Access for High-Frequency Filters
Query execution over cached data SHALL use prebuilt indexes for known high-frequency filter columns. Indexed columns SHALL include: `WORKCENTER_GROUP`, `PACKAGE_LEF`, `PJ_TYPE`, `FIRSTNAME`, `WAFERDESC`, `WIP_STATUS`, `HOLD_TYPE`, `LOTID`, `WORKORDER`.

#### Scenario: Filtered report query
- **WHEN** request filters target indexed fields
- **THEN** result selection MUST avoid full dataset scans and maintain existing response contract

#### Scenario: LOTID and WORKORDER use indexed access
- **WHEN** request includes `lotid` or `workorder` filter values
- **THEN** filtering MUST use the pre-built `lotid` / `workorder` index via `_lookup_positions()`
- **THEN** `_contains_any_mask()` with `str.contains()` MUST NOT be called for these fields
