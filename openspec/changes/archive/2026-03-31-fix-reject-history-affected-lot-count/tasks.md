## 1. Fix backend DuckDB spool runtime

- [x] 1.1 Update `lot_expr` in `try_compute_view_from_spool()` analytics query (~line 701): use `COUNT(DISTINCT "CONTAINERID")` when `AFFECTED_LOT_COUNT` is absent but `CONTAINERID` is present
- [x] 1.2 Update `lot_expr` in `try_compute_batch_pareto_from_spool()` (~line 534): same fix as 1.1

## 2. Verify

- [x] 2.1 Run existing reject-history tests to ensure no regressions
