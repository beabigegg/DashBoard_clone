# oracle-query-fragment-governance Specification

## Purpose
TBD - created by archiving change residual-hardening-round4. Update Purpose after archive.
## Requirements
### Requirement: Shared Oracle Query Fragments SHALL Have a Single Source of Truth
Cross-service Oracle query fragments for resource and equipment cache loading MUST be defined in a shared module and imported by service implementations.

#### Scenario: Update common table/view reference
- **WHEN** a common table or view name changes
- **THEN** operators and developers MUST be able to update one shared definition without editing duplicated SQL literals across services

### Requirement: Service Queries MUST Preserve Existing Columns and Semantics
Services consuming shared Oracle query fragments SHALL preserve existing selected columns, filters, and downstream payload behavior.

#### Scenario: Resource and equipment cache refresh after refactor
- **WHEN** cache services execute queries via shared fragments
- **THEN** resulting payload structure MUST remain compatible with existing aggregation and API contracts

