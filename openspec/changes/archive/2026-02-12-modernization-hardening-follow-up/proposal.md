## Why

Recent code review on the Phase 1 modernization delivery found several high-risk consistency gaps: mutable cached policy payloads, inconsistent fallback-retirement error behavior, aggressive `.env.example` defaults, and route-governance drift risks between backend JSON and frontend contract definitions. These issues can cause environment-dependent startup failures, silent policy drift, and hard-to-debug runtime behavior.

## What Changes

- Harden modernization policy loaders to prevent shared mutable cache corruption and make refresh semantics explicit/documented.
- Unify in-scope fallback-retirement response behavior across app-level routes and blueprint routes.
- Make `.env.example` safe for local onboarding while still documenting production-recommended hardening values.
- Consolidate feature-flag boolean resolution (`env > config > default`) into a shared helper and remove duplicated `_to_bool` implementations.
- Add route-contract cross-validation between backend contract artifacts and frontend `routeContracts.js` inventory.
- Add explicit warning telemetry when legacy shell-contract artifact fallback is used.
- Document and test intentional canonical-redirect scope asymmetry (report routes vs admin external targets).
- Reduce avoidable redirect chain length for `/hold-detail` missing-reason flow in SPA mode.
- Add shell-token fallback values for QC-GATE page CSS variables to prevent rendering degradation outside shell context.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `asset-readiness-and-fallback-retirement`: unify fallback-retirement failure surfaces and safe local defaults for readiness-related flags.
- `frontend-platform-modernization-governance`: add governance requirements for contract-source consistency and legacy artifact fallback observability.
- `spa-shell-navigation`: document and enforce canonical redirect scope rules, including missing-reason redirect behavior.
- `unified-shell-route-coverage`: require frontend/backend route-contract set consistency checks.
- `style-isolation-and-token-enforcement`: require token fallback behavior for route-local styles that may render outside shell variable scope.
- `maintainability-type-and-constant-hygiene`: require shared feature-flag and boolean parsing helpers for policy/runtime modules.

## Impact

- Affected backend modules: `src/mes_dashboard/core/modernization_policy.py`, `src/mes_dashboard/core/runtime_contract.py`, `src/mes_dashboard/app.py`, hold-related routes.
- Affected frontend modules: `frontend/src/portal-shell/routeContracts.js`, `frontend/src/qc-gate/style.css`.
- Affected governance and tests: modernization gate script/tests, route-contract consistency tests, redirect/fallback behavior tests, `.env.example` documentation.
