## ADDED Requirements

### Requirement: Recursive Payload Cleaning MUST Enforce Depth Safety
Routes that normalize nested payloads MUST prevent unbounded recursion depth.

#### Scenario: Deeply nested response object
- **WHEN** NaN-cleaning helper receives deeply nested list/dict payload
- **THEN** cleaning logic MUST enforce max depth or iterative traversal and return safely without recursion failure

### Requirement: Filter Source Names MUST Be Configurable
Filter cache query sources MUST NOT rely on hardcoded view names only.

#### Scenario: Environment-specific view names
- **WHEN** deployment sets custom filter-source environment variables
- **THEN** filter cache loader MUST resolve and query configured view names

### Requirement: High-Cost APIs SHALL Apply Basic Rate Guardrails
High-cost read endpoints SHALL apply configurable request-rate guardrails to reduce abuse and accidental bursts.

#### Scenario: Burst traffic from same client
- **WHEN** a client exceeds configured request budget for guarded endpoints
- **THEN** endpoint SHALL return throttled response with clear retry guidance

### Requirement: Common Boolean Query Parsing SHALL Be Shared
Boolean query parsing in routes SHALL use shared helper behavior.

#### Scenario: Different routes parse include flags
- **WHEN** routes parse common boolean query parameters
- **THEN** parsing behavior MUST be consistent across routes via shared utility
