## ADDED Requirements

### Requirement: WIP cache observability SHALL report against the canonical Parquet key
Admin and diagnostics endpoints SHALL inspect the same canonical WIP Parquet key used by runtime read/write helpers so cache telemetry remains operationally interpretable.

#### Scenario: Admin API samples WIP namespace memory
- **WHEN** `/admin/api/performance-detail` estimates Redis memory for the `mes_wip` namespace
- **THEN** it SHALL sample the canonical `mes_wip:data:parquet` key
- **THEN** it SHALL NOT sample a double-prefixed or legacy JSON key as the representative WIP payload

#### Scenario: Runtime and observability compare the same WIP key
- **WHEN** operators compare runtime cache behavior with admin/health telemetry
- **THEN** both surfaces SHALL refer to the same canonical WIP Parquet key
- **THEN** discrepancies caused only by key naming drift SHALL NOT occur
