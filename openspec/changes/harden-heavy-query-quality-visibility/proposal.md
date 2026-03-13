## Why

Heavy-query paths already implement OOM protections (chunking, spool, and DuckDB/cache-sql fallback) in several modules, but data-completeness visibility is still inconsistent across routes and UI paths. In particular, some single-item EventFetcher endpoints and legacy MSD summary paths can return data without surfacing non-complete states to users, creating a residual silent-missing-data risk.

## What Changes

- Unify EventFetcher completeness propagation for query-tool detail APIs so single-item and batch-item paths both return `quality_meta` consistently.
- Require query-tool detail UI to show explicit warning banners whenever `quality_meta.status` is `partial` or `truncated`, regardless of single/batch mode.
- Align MSD user-visible warnings with staged trace completeness metadata (`quality_meta`), not only genealogy error state.
- Define a migration contract for MSD UI/runtime path selection so the staged trace path is the canonical source of completeness signaling for heavy queries.
- Add regression coverage to prevent future drift between normal path vs fallback path completeness behavior.

## Capabilities

### New Capabilities
- `heavy-query-quality-visibility-migration`: Defines migration and parity requirements for heavy-query completeness visibility across legacy and staged paths.

### Modified Capabilities
- `query-tool-lot-trace`: Ensure all EventFetcher-backed detail responses (single and batch) expose `quality_meta` and UI warning parity.
- `msd-analysis-transparency`: Ensure MSD page displays visible non-complete-result warning based on `quality_meta`, in addition to genealogy failure messaging.
- `query-result-integrity-contract`: Strengthen contract language for parity between single/batch, sync/async, and legacy/staged transports.
- `trace-staged-api`: Clarify completeness metadata obligations for staged events responses used by MSD/query-tool flows.

## Impact

- Backend routes/services:
  - `src/mes_dashboard/services/query_tool_service.py`
  - `src/mes_dashboard/routes/query_tool_routes.py`
  - `src/mes_dashboard/routes/trace_routes.py`
  - `src/mes_dashboard/services/mid_section_defect_service.py`
  - `src/mes_dashboard/routes/mid_section_defect_routes.py`
- Frontend:
  - `frontend/src/query-tool/composables/useLotDetail.js`
  - `frontend/src/query-tool/components/LotDetail.vue`
  - `frontend/src/mid-section-defect/App.vue`
  - `frontend/src/shared-composables/useTraceProgress.js`
- Tests:
  - `tests/test_query_tool_routes.py`
  - `tests/test_mid_section_defect_routes.py`
  - `frontend/tests/query-tool-composables.test.js`
  - MSD frontend/unit tests for quality-warning rendering
- Operational behavior:
  - No DB schema change.
  - No removal of existing OOM guards/chunking policy.
  - Emphasis on metadata parity and user-visible warning consistency.
