## 1. Backend lineage model (typed graph)

- [x] 1.1 Extend `LineageEngine` output to include typed `nodes` and `edges` while keeping legacy-compatible fields
- [x] 1.2 Implement edge builders for `wafer_origin` (via `DW_MES_CONTAINER.FIRSTNAME`) and `gd_rework_source` (via `ORIGINALCONTAINERID`, fallback `SPLITFROMID`)
- [x] 1.3 Add node classification helper for `WAFER/GC/GA/GD/SERIAL` and ensure deterministic priority rules
- [x] 1.4 Add/adjust SQL fragments needed for wafer-origin and GD-source resolution with bind-safe `QueryBuilder` usage

## 2. Trace API and resolve contract updates

- [x] 2.1 Extend resolve service to support `wafer_lot`, `gd_work_order`, and `gd_lot_id` input types with profile-aware validation
- [x] 2.2 Update `/api/trace/seed-resolve` to enforce profile-specific resolve-type allowlists (`query_tool` vs `query_tool_reverse`)
- [x] 2.3 Update `/api/trace/lineage` response contract to return typed graph payload additively (no immediate legacy break)
- [x] 2.4 Verify lineage cache behavior remains profile-safe and does not mix forward/reverse responses

## 3. Query-tool frontend integration

- [x] 3.1 Update query bars and tab logic to expose forward types (`wafer_lot/lot_id/work_order`) and reverse types (`serial_number/gd_work_order/gd_lot_id`)
- [x] 3.2 Refactor lineage composables to consume typed graph fields and map them into rendering data structures
- [x] 3.3 Update `LineageTreeChart` to render semantic node styles and edge semantics for split/merge/wafer/gd-rework
- [x] 3.4 Implement explicit UI handling for GC-optional flow (`WAFER -> GA` visible when GC is absent)
- [x] 3.5 Ensure node click only updates detail scope and does not mutate tree visibility

## 4. Validation, regression, and documentation

- [x] 4.1 Add backend tests for resolve-type validation (`gd_work_order` + `gd_lot_id`), wafer-origin edges, and GD-source linkage
- [x] 4.2 Add API contract tests for typed lineage fields and backward-compatible fields
- [x] 4.3 Run manual data validation on representative scenarios:
- [x] 4.4 Validate `WAFER -> GA` path without GC
- [x] 4.5 Validate `WAFER -> GC -> GA` path
- [x] 4.6 Validate `SERIAL -> GD -> source lot -> WAFER` reverse path
- [x] 4.7 Update user-facing documentation/help text for new query modes and GD/GC interpretation rules
