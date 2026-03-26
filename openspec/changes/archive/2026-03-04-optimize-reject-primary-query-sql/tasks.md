## 1. Primary SQL Source Isolation

- [x] 1.1 Add a dedicated reject-history primary SQL file under `src/mes_dashboard/sql/reject_history/` without paginated list operators
- [x] 1.2 Ensure the new SQL template preserves the column contract required by dataset-cache derivation (`summary`/`trend`/`detail`/`pareto`)
- [x] 1.3 Keep `src/mes_dashboard/sql/reject_history/list.sql` unchanged for legacy paginated list use

## 2. Service Path Decoupling

- [x] 2.1 Update `reject_dataset_cache.execute_primary_query()` direct path to compile and execute the dedicated primary SQL template
- [x] 2.2 Update reject-history batch chunk execution path to use the dedicated primary SQL template
- [x] 2.3 Remove reject chunk data assembly logic that depends on `offset/limit` pagination replay
- [x] 2.4 Preserve existing cache/spool write path and response shape (`query_id`, `summary`, `trend`, `detail`, `available_filters`, `meta`)

## 3. Compatibility and Resilience Guards

- [x] 3.1 Verify `query_list()` and `GET /api/reject-history/list` pagination behavior remains unchanged
- [x] 3.2 Verify partial-failure metadata behavior remains unchanged for batch mode (`has_partial_failure`, failed chunks/ranges)
- [x] 3.3 Add defensive logging/diagnostics confirming primary query source path selection for troubleshooting

## 4. Tests and Verification

- [x] 4.1 Add or update unit tests in `tests/test_reject_dataset_cache.py` to assert primary/chunk paths no longer require `offset/limit`
- [x] 4.2 Add or update tests in `tests/test_reject_history_service.py` and `tests/test_reject_history_routes.py` to assert `/list` contract compatibility
- [x] 4.3 Run targeted test suite for reject-history cache/service/routes and batch resilience coverage
- [ ] 4.4 Perform manual validation of large-range reject-history query latency and ensure no frontend timeout regression (requires integration env + Oracle data + frontend flow)
