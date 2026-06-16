# Change Request

## Original Request

Add typed response schemas to all 158 API endpoints (ADR 0007 Response-shape migration): declare typed ## Schemas in api-contract.md for every endpoint, generate openapi.json, capture real Flask test-client samples for each endpoint into tests/contract/samples/, create tests/contract/response-samples.json manifest, and wire cdd-kit validate --contracts to enforce data-shape conformance. Success criterion: cdd-kit doctor reports 0 warnings on Response-shape; cdd-kit validate --contracts passes with all samples validated.

User confirmed scope: all 158 endpoints.

## Business / User Goal

## Non-goals

## Constraints

## Known Context

## Open Questions

## Requested Delivery Date / Priority
