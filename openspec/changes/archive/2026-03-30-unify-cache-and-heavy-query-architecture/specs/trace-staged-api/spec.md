## MODIFIED Requirements

### Requirement: Staged trace API SHALL prefer the spool-safe async path for heavy events work
`POST /api/trace/events` SHALL use canonical spool-backed heavy-query storage for reusable or large event results, while Redis remains limited to job state, progress, manifests, and lightweight replay metadata.

#### Scenario: Existing reusable result available
- **WHEN** the events request matches a valid canonical spool-backed result
- **THEN** the endpoint SHALL serve the result from the canonical staged dataset without rerunning Oracle work

#### Scenario: No reusable result available
- **WHEN** the events request has no reusable staged dataset
- **THEN** the endpoint SHALL enqueue the events work to the async heavy-query pipeline and return HTTP 202 for the async-capable path

#### Scenario: Result persistence after async completion
- **WHEN** a heavy trace events job completes
- **THEN** the replayable result body SHALL be persisted as spool-backed heavy-query storage
- **THEN** Redis SHALL retain only job metadata, progress, and lightweight result-manifest state

## ADDED Requirements

### Requirement: Trace lineage results SHALL use heavy-query result storage when replayable or large
Trace lineage flows SHALL use spool-backed result storage for replayable or large lineage results instead of treating large Redis JSON payloads as the canonical result body.

#### Scenario: Reusable lineage result
- **WHEN** a lineage request produces a replayable result graph that may be polled or re-read
- **THEN** the canonical lineage result body SHALL be stored in heavy-query storage
- **THEN** Redis SHALL store only query identity, job status, and lightweight reconstruction metadata

#### Scenario: Lineage result endpoint
- **WHEN** a client fetches lineage job results
- **THEN** the endpoint SHALL reconstruct or stream the response from the canonical lineage result storage
- **THEN** the client-visible response contract SHALL remain compatible with staged trace APIs
