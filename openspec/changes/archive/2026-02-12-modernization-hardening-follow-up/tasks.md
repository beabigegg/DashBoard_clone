## 1. Shared Flag and Policy Helper Hardening

- [x] 1.1 Introduce shared boolean parsing and feature-flag resolution helpers (`env > config > default`) in a common core utility module.
- [x] 1.2 Replace duplicated `_to_bool` / inline bool parsing in `app.py`, `modernization_policy.py`, and `runtime_contract.py` with shared helpers.
- [x] 1.3 Refactor modernization policy cached JSON loaders to prevent shared mutable-state corruption (defensive return strategy + clear cache helper for controlled refresh/testing).
- [x] 1.4 Add inline documentation comments describing policy cache refresh behavior and operator expectations.

## 2. Fallback and Redirect Behavior Consistency

- [x] 2.1 Implement a shared retired-fallback response helper usable by both app-level and blueprint-level route handlers.
- [x] 2.2 Migrate hold-related blueprint routes (`hold-overview`, `hold-history`, `hold-detail`) to the shared retired-fallback response contract.
- [x] 2.3 Update `/hold-detail` missing-`reason` logic to single-hop redirect to canonical shell overview when SPA shell mode is enabled.
- [x] 2.4 Document canonical redirect scope boundaries (report routes only, admin external targets excluded) in policy code comments.

## 3. Environment and Governance Documentation Safety

- [x] 3.1 Update `.env.example` modernization/runtime hardening flags to onboarding-safe defaults for local environments.
- [x] 3.2 Add explicit production-recommended values and rationale comments next to each adjusted flag in `.env.example`.
- [x] 3.3 Update modernization governance docs to clarify policy artifact cache refresh/invalidation model.

## 4. Route Contract Drift Detection and Observability

- [x] 4.1 Extend modernization governance checks to cross-validate backend route contract artifacts against frontend `routeContracts.js` route inventory and scope classifications.
- [x] 4.2 Add/extend tests that fail on frontend-backend route set drift and scope mismatch.
- [x] 4.3 Emit explicit warning logs when shell contract loading falls back to a legacy contract artifact path.
- [x] 4.4 Add test coverage verifying legacy contract fallback warning behavior.

## 5. Style Token Fallback Resilience

- [x] 5.1 Update QC-GATE route-local CSS variables that depend on shell tokens to include fallback values.
- [x] 5.2 Add style-governance check or test assertion that shell-derived route styles include fallback values unless explicitly exempted.

## 6. Test Coverage and Regression Validation

- [x] 6.1 Add redirect compatibility tests for non-ASCII query parameters through canonical redirect flows.
- [x] 6.2 Add explicit test for `/hold-detail` missing-`reason` redirect chain behavior under SPA enabled mode.
- [x] 6.3 Narrow broad `os.path.exists` patches in route/template tests to targeted path-specific behavior where feasible.
- [x] 6.4 Run relevant unit/integration/frontend/e2e governance test suites and record pass criteria for this hardening change.

## Validation Record

- `pytest -q tests/test_feature_flags.py tests/test_modernization_policy_hardening.py tests/test_asset_readiness_policy.py tests/test_hold_routes.py tests/test_portal_shell_routes.py tests/test_full_modernization_gates.py tests/test_template_integration.py` → `84 passed`
- `pytest -q tests/test_hold_overview_routes.py tests/test_hold_history_routes.py` → `34 passed`
- `pytest -q tests/test_wip_routes.py` → `27 passed`
- `pytest -q tests/test_runtime_contract.py tests/test_runtime_hardening.py -k "runtime_contract or runtime"` → `10 passed`
- `pytest -q tests/test_wip_hold_pages_integration.py` → `3 passed`
- `npm --prefix frontend test` → `64 passed`
- `python scripts/check_full_modernization_gates.py --mode block` → `[OK] modernization gates passed`
- `E2E_BASE_URL=http://127.0.0.1:8091 pytest -q tests/e2e/test_wip_hold_pages_e2e.py -k "hold_detail_without_reason_redirects_to_overview" --run-e2e` → `1 passed`
- `STRESS_TEST_URL=http://127.0.0.1:8091 STRESS_CONCURRENT_USERS=2 STRESS_REQUESTS_PER_USER=3 pytest -q tests/stress/test_api_load.py -k "hold_detail_lots_concurrent_load"` → `1 passed`
