## MODIFIED Requirements

### Requirement: Staged trace API SHALL expose seed-resolve endpoint
`POST /api/trace/seed-resolve` SHALL resolve seed lots based on profile-specific resolve types.

#### Scenario: Forward profile resolve types
- **WHEN** request body contains `{ "profile": "query_tool", "params": { "resolve_type": "<type>", "values": [...] } }`
- **THEN** `<type>` SHALL be one of `wafer_lot`, `lot_id`, or `work_order`
- **THEN** non-supported types for this profile SHALL return HTTP 400 with `INVALID_PARAMS`

#### Scenario: Reverse profile resolve types
- **WHEN** request body contains `{ "profile": "query_tool_reverse", "params": { "resolve_type": "<type>", "values": [...] } }`
- **THEN** `<type>` SHALL be one of `serial_number`, `gd_work_order`, or `gd_lot_id`
- **THEN** invalid `gd_work_order` values not matching `GD%` SHALL return HTTP 400

#### Scenario: GD lot-id validation
- **WHEN** reverse profile uses `resolve_type=gd_lot_id`
- **THEN** each value SHALL be validated against GD lot rules before resolution
- **THEN** invalid values SHALL return HTTP 400 with `INVALID_PARAMS`

#### Scenario: Seed response payload compatibility
- **WHEN** seed resolution succeeds
- **THEN** response SHALL include `stage`, `seeds`, `seed_count`, and `cache_key`
- **THEN** each seed SHALL include `container_id` and displayable lot/container name fields

### Requirement: Staged trace API SHALL expose lineage endpoint
`POST /api/trace/lineage` SHALL return semantic lineage graph fields while preserving legacy-compatible fields during migration.

#### Scenario: Lineage response contains typed graph fields
- **WHEN** lineage is resolved for `query_tool` or `query_tool_reverse`
- **THEN** response SHALL include typed lineage fields (`nodes` and typed `edges`)
- **THEN** each edge SHALL declare edge type sufficient to distinguish split/merge/wafer/gd-rework

#### Scenario: Legacy compatibility during frontend migration
- **WHEN** existing clients still consume legacy lineage fields
- **THEN** lineage response SHALL continue to include existing compatibility fields for a migration period
- **THEN** typed fields SHALL be additive and not break current clients

#### Scenario: Profile-aware cache keys
- **WHEN** lineage requests have same container IDs but different profiles
- **THEN** cache keys SHALL remain profile-aware to prevent cross-profile response mixing
- **THEN** repeated requests with same profile and same sorted IDs SHALL hit cache
