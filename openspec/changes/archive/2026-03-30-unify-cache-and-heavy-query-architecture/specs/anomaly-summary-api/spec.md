## ADDED Requirements

### Requirement: Anomaly computation SHALL consume canonical source dataset identities
The anomaly layer SHALL compute derived results from canonical source dataset identities and SHALL not act as the owner of source dataset warmup for user-facing heavy-query domains.

#### Scenario: Source dataset already available
- **WHEN** anomaly computation begins and the required canonical source datasets already exist
- **THEN** the anomaly layer SHALL consume those canonical source dataset identities to compute derived results

#### Scenario: Source dataset unavailable
- **WHEN** anomaly computation cannot resolve a required canonical source dataset
- **THEN** the anomaly layer SHALL report the source dataset as unavailable or degraded
- **THEN** the anomaly layer SHALL not become the implicit steady-state warmup mechanism for that source dataset

### Requirement: Anomaly summary and detail payloads SHALL be treated as derived-result cache
Anomaly summary and detector detail payloads SHALL be stored as compact derived results rather than as source dataset substitutes.

#### Scenario: Derived result publication
- **WHEN** anomaly computation completes
- **THEN** Redis MAY store summary and detector detail payloads for replay
- **THEN** those payloads SHALL remain materially smaller than the underlying source datasets
- **THEN** clients SHALL not treat anomaly payloads as a replacement for the source heavy-query datasets
