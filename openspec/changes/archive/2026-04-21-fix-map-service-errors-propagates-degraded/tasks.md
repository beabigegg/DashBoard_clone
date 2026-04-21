## 1. Update degraded-error propagation

- [x] 1.1 Import `DatabaseDegradedError` into `src/mes_dashboard/routes/query_tool_routes.py`.
- [x] 1.2 Add a re-raise branch in `map_service_errors` so degraded database exceptions bypass the generic `internal_error()` catch-all.

## 2. Flip the Oracle degraded tests from pinning to contract checks

- [x] 2.1 Rewrite the degraded query-tool tests in `tests/integration/test_oracle_error_path.py` to assert `503` plus the expected machine-readable error code and `Retry-After`.
- [x] 2.2 Keep the existing typed-service-error branches (`UserInputError`, `ResourceNotFoundError`, `QueryTimeoutError`, etc.) unchanged and covered.

## 3. Verify query-tool degraded behavior

- [x] 3.1 Run the focused Oracle degraded integration tests covering query-tool routes.
- [x] 3.2 Run affected query-tool route tests to confirm non-degraded exception mapping remains stable.
