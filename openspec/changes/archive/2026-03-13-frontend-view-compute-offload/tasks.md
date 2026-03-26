## 1. Backend Activation Metadata

- [x] 1.1 Add shared spool metadata injection for Resource History query/view responses, including `spool_download_url` and `total_row_count` when eligible.
- [x] 1.2 Add shared spool metadata injection for Hold History query/view responses, including `spool_download_url` and `total_row_count` when eligible.
- [x] 1.3 Add page-level feature flags and safety thresholds for Resource History and Hold History local-compute activation.
- [x] 1.4 Preserve current response envelopes and fallback semantics (`cache_expired`, spool expiry, server `/view`) while exposing local-compute eligibility metadata.

## 2. Shared Frontend Runtime

- [x] 2.1 Refine shared DuckDB client/worker utilities so additional pages can reuse activation, registration, teardown, and error handling consistently.
- [x] 2.2 Create a small shared activation policy helper for browser support, thresholds, and fallback decisions.
- [x] 2.3 Add shared handling for spool-expired/download-failed transitions so pages can revert cleanly to server `/view` mode or re-run the primary query.

## 3. Resource History Local Compute

- [x] 3.1 Implement a `resource-history` local-compute composable/module that derives KPI, trend, heatmap, workcenter comparison, and detail views from Parquet spool data.
- [x] 3.2 Update the Resource History page orchestration to activate local mode after `POST /query` when eligible and skip `/view` requests for supplementary interactions.
- [x] 3.3 Preserve server `/view` fallback behavior for unsupported browsers, disabled flags, download failures, and cache/spool expiry.
- [x] 3.4 Keep URL sync, filter pruning, and pagination behavior consistent across local and server modes.

## 4. Hold History Local Compute

- [x] 4.1 Implement a `hold-history` local-compute composable/module that derives trend, reason pareto, duration distribution, and paginated list views from Parquet spool data.
- [x] 4.2 Update the Hold History page orchestration to activate local mode after `POST /query` when eligible and skip `/view` requests for supplementary interactions.
- [x] 4.3 Preserve server `/view` fallback behavior for unsupported browsers, disabled flags, download failures, and cache/spool expiry.
- [x] 4.4 Keep pagination overlay, request guard, and URL state behavior consistent across local and server modes.

## 5. Verification and Rollout

- [x] 5.1 Add parity tests comparing Resource History frontend derivation against the existing server-side reference outputs.
- [x] 5.2 Add parity tests comparing Hold History frontend derivation against the existing server-side reference outputs.
- [x] 5.3 Add frontend integration/stress coverage proving that local mode suppresses supplementary `/view` requests when active and falls back safely when not active.
- [x] 5.4 Record rollout notes, feature-flag defaults, and rollback expectations so the change can be enabled incrementally.
