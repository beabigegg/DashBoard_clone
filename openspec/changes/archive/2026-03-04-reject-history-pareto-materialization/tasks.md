## 1. Materialization Service Foundation

- [x] 1.1 Create a dedicated reject Pareto materialization service module with key builder, payload schema versioning, and read/write interfaces
- [x] 1.2 Implement canonical filter-context hashing (policy toggles, supplementary filters, trend dates) for materialized snapshot key isolation
- [x] 1.3 Implement single-flight guard for concurrent snapshot builds targeting the same key
- [x] 1.4 Add TTL and payload-size guardrails for materialized snapshots with explicit rejection paths

## 2. Snapshot Build and Compute Path

- [x] 2.1 Implement snapshot build pipeline from cached reject dataset to six-dimension aggregate structures
- [x] 2.2 Implement cross-filter evaluation on materialized structures with exclude-self parity to current batch Pareto behavior
- [x] 2.3 Implement `pareto_scope` (`top80`/`all`) and `pareto_display_scope` compatibility on materialized outputs
- [x] 2.4 Add deterministic invalidation rules for stale or schema-mismatched snapshots

## 3. API Integration and Compatibility

- [x] 3.1 Integrate materialized read-through path into `compute_batch_pareto` and cached `compute_dimension_pareto` flow
- [x] 3.2 Implement safe fallback to legacy DataFrame-based compute when snapshot is missing, stale, or build fails
- [x] 3.3 Add response metadata fields for materialized source/freshness/version and fallback reason codes without breaking existing payload schema
- [x] 3.4 Ensure cache-miss behavior for missing `query_id` remains unchanged (no Oracle fallback)

## 4. Observability and Operations Signals

- [x] 4.1 Extend cache telemetry payload to include materialized hit/miss/build/fallback counters and rates
- [x] 4.2 Add snapshot freshness and payload-size telemetry fields to deep health diagnostics
- [x] 4.3 Emit and document stable fallback reason codes (`miss`, `stale`, `build_failed`, etc.) for alert correlation
- [x] 4.4 Add logging hooks for build latency and build failure diagnostics with request/key correlation context

## 5. Validation, Rollout, and Regression Safety

- [x] 5.1 Add unit tests for key isolation, schema version invalidation, single-flight behavior, and guardrail enforcement
- [x] 5.2 Add parity tests comparing materialized and legacy results across multi-dimension cross-filter scenarios
- [x] 5.3 Add route/service tests validating metadata exposure and fallback behavior under snapshot miss/stale/build-failure paths
- [x] 5.4 Execute reject-history regression suite and stress checks for repeated Pareto filter toggling to confirm lower worker memory pressure
- [x] 5.5 Add feature-flagged rollout plan (telemetry-only -> read-through enabled -> default-on) with rollback switch
