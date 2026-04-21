## 1. Add shared validation primitives

- [x] 1.1 Identify or extract shared helpers for strict date parsing, inverted-range checks, and text-filter hygiene.
- [x] 1.2 Ensure all new validation failures use `mes_dashboard.core.response.validation_error()` rather than manual JSON responses.

## 2. Harden the affected routes

- [x] 2.1 Add route-boundary validation for `start_date`/`end_date` on `/api/reject-history/options`.
- [x] 2.2 Add route-boundary validation for `workcenter_group` on `/api/hold-overview/summary`.
- [x] 2.3 Add route-boundary validation for `workcenter_group` on `/api/wip/overview/summary`.

## 3. Tighten regression coverage

- [x] 3.1 Remove the temporary `xfail` markers from the three strict fuzz tests in `tests/routes/test_fuzz_routes.py`.
- [x] 3.2 Run the targeted fuzz tests for reject-history, hold-overview, and wip-overview summary validation.
- [x] 3.3 Run affected happy-path route tests to confirm valid inputs still return unchanged 200 responses.
