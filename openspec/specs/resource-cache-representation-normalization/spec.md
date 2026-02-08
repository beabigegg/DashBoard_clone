# resource-cache-representation-normalization Specification

## Purpose
TBD - created by archiving change residual-hardening-round4. Update Purpose after archive.
## Requirements
### Requirement: Resource Derived Index MUST Avoid Full Record Duplication
Resource derived index SHALL use lightweight row-position references instead of storing full duplicated record payloads alongside the process DataFrame cache.

#### Scenario: Build index from cached DataFrame
- **WHEN** resource cache data is parsed from Redis into process-level DataFrame
- **THEN** the derived index MUST store position-based references and metadata without a second full records copy

### Requirement: Resource Query APIs SHALL Preserve Existing Response Contract
Resource query APIs MUST keep existing output fields and semantics after index representation normalization.

#### Scenario: Read all resources after normalization
- **WHEN** callers request all resources or filtered resource lists
- **THEN** the returned payload MUST remain field-compatible with pre-normalization responses

### Requirement: Cache Invalidation MUST Keep Index/Data Coherent
The system SHALL invalidate and rebuild DataFrame/index representations atomically at cache refresh boundaries.

#### Scenario: Redis-backed cache refresh completes
- **WHEN** a new resource cache snapshot is published
- **THEN** stale index references MUST be invalidated before subsequent reads use refreshed DataFrame data

