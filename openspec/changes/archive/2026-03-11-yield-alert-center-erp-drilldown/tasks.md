## 1. Data Contracts and Query Foundations

- [x] 1.1 Define request/response schemas for yield aggregate, alert list, and drilldown payload (including cache/linkage metadata fields).
- [x] 1.2 Implement Oracle query fragments for `ERP_WIP_MOVETXN` baseline aggregates and `ERP_WIP_MOVETXN_DETAIL` dimension aggregates.
- [x] 1.3 Add backend validation for max date-window, allowed sort keys, and page/per_page bounds.
- [x] 1.4 Add normalized query-key builder for cache reuse across equivalent requests.

## 2. Linkage Service (ERP -> Reject History)

- [x] 2.1 Implement canonical key builder using `date_bucket + workorder + normalized_reason_code`.
- [x] 2.2 Implement reason code normalization map and unknown-code fallback (`unmapped_reason`).
- [x] 2.3 Implement linkage match-quality metrics output (`matched`, `unmatched`, `partially_matched`, quantity totals, warning flags).
- [x] 2.4 Implement drilldown payload generation with explicit `match_status` (`exact`, `partial`, `none`) and fallback reason metadata.

## 3. Yield Alert Center API Endpoints

- [x] 3.1 Add new API routes for yield summary/trend and alert candidate list with deterministic pagination output.
- [x] 3.2 Integrate cache hit/miss metadata in API responses.
- [x] 3.3 Integrate linkage service into alert row drilldown context endpoint.
- [x] 3.4 Add error-handling contract for validation failures and time-window policy violations.

## 4. Frontend Page and Interaction Flow

- [x] 4.1 Add new navigation entry and route for Yield Alert Center without changing existing Reject History route behavior.
- [x] 4.2 Build page filter panel and local state model isolated from Reject History state.
- [x] 4.3 Build trend cards/charts and alert table UI bound to new APIs with loading/empty/error states.
- [x] 4.4 Implement row-level drilldown action that passes normalized linkage keys and surfaces partial-match warning.
- [x] 4.5 Add retry/refresh actions and ensure repeated submits are throttled while request is in-flight.

## 5. Quality Gates, Rollout, and Documentation

- [x] 5.1 Add unit tests for query validation, canonical key generation, reason normalization, and linkage status logic.
- [x] 5.2 Add API integration tests for pagination, metadata contract, and drilldown payload behavior.
- [x] 5.3 Add frontend tests for route isolation, feedback states, and drilldown interaction.
- [x] 5.4 Add observability metrics/logging for Oracle latency, cache hit ratio, and unmatched linkage ratio.
- [x] 5.5 Document feature flag rollout, rollback steps, and operator runbook notes for tuning window/page limits.
