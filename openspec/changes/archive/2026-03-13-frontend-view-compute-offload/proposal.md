## Why

The current MES dashboard already avoids repeat Oracle queries on several report pages, but many supplementary view updates still consume Flask worker CPU and memory for server-side derivation. Resource History and Hold History already produce cacheable Parquet spools, so this is the right time to extend the proven browser-side compute pattern used by Reject History and Yield Alert to reduce `/view` load without changing primary query semantics.

## What Changes

- Extend the existing DuckDB-WASM frontend compute pattern to `resource-history` and `hold-history`.
- Add a shared activation policy so two-phase pages can choose between local view computation and server `/view` fallback based on browser support, spool availability, and dataset size.
- Update Resource History and Hold History page behavior so supplementary filters and pagination prefer browser-side computation after `POST /query` succeeds.
- Preserve server-side `/view` endpoints as compatibility and fallback paths when local compute cannot be activated.
- Add parity, fallback, and performance coverage for the new client-side computation paths.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `frontend-duckdb-wasm`: expand the client-side DuckDB contract from reject-history and yield-alert to additional two-phase report pages with shared activation and fallback behavior.
- `resource-history-page`: change supplementary view updates so the page may compute summary/detail locally from Parquet spool instead of always calling `GET /view`.
- `hold-history-page`: change supplementary view updates so the page may compute trend/pareto/duration/list locally from Parquet spool instead of always calling `GET /view`.

## Impact

- Frontend: `frontend/src/resource-history`, `frontend/src/hold-history`, shared DuckDB client/worker utilities, and page-level filter/pagination orchestration.
- Backend API: Resource History and Hold History query/view responses and spool metadata exposure must support browser-side activation while preserving current response envelopes.
- Backend services: Existing Parquet spool and DuckDB runtime modules remain the fallback path and parity reference, but should no longer be the preferred path for every supplementary interaction.
- Quality gates: parity tests, frontend stress/performance coverage, and fallback handling for expired/missing spools or unsupported browsers.
