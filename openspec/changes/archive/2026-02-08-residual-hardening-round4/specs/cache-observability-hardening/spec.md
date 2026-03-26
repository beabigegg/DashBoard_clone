## MODIFIED Requirements

### Requirement: Cache Telemetry SHALL Include Memory Amplification Signals
Operational telemetry MUST expose cache-domain memory usage indicators and representation amplification factors, and MUST differentiate between authoritative data payload and derived/index helper structures.

#### Scenario: Deep health telemetry request after representation normalization
- **WHEN** operators inspect cache telemetry for resource or WIP domains
- **THEN** telemetry MUST include per-domain memory footprint, amplification indicators, and enough structure detail to verify that full-record duplication is not reintroduced
