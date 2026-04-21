## 1. Add Oracle app-level mapping

- [x] 1.1 Implement an app-level Oracle-driver error handler in `src/mes_dashboard/app.py` above the generic `Exception` handler.
- [x] 1.2 Reuse `_extract_ora_code()` to dispatch known ORA codes to the appropriate response helpers and retry semantics.
- [x] 1.3 Add any required response helper/code to distinguish unknown ORA failures from generic application failures.

## 2. Cover mapped Oracle behaviors

- [x] 2.1 Rewrite the ORA pinning tests in `tests/integration/test_oracle_error_path.py` to assert the mapped behaviors for ORA-01017, ORA-12514, and ORA-01555.
- [x] 2.2 Add or update focused tests for unknown ORA fallback behavior so database-originated 500s remain distinguishable from generic internal errors.

## 3. Verify end-to-end response contracts

- [x] 3.1 Run the focused Oracle request-path integration tests for mapped ORA responses.
- [x] 3.2 Run affected backend response-contract and route tests to confirm happy-path and non-Oracle exception handling remain unchanged.
