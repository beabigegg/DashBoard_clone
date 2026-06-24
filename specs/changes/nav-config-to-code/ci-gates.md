# CI/CD Gate Plan — nav-config-to-code

## Change ID
nav-config-to-code

## Required Gates for This Change

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|---:|---|---|---|
| response-shape-validate | 1 | yes | push / PR | `cdd-kit validate --contracts` (after drawer samples retired from `tests/contract/response-samples.json`) | — |
| unit-mock-integration | 1 | yes | push / PR | `pytest -m "not (e2e or integration_real or stress or load or soak or multi_worker)" --ignore=tests/integration --ignore=tests/stress --ignore=tests/e2e --ignore=tests/manual -x` | junit XML |
| frontend-unit | 1 | yes | push / PR | `cd frontend && npm run test` | vitest report |
| playwright-critical-journeys | 1 | yes | PR | `cd frontend && npx playwright test tests/playwright/admin-pages.spec.ts tests/playwright/portal-shell-login.spec.ts` | playwright trace |
| openapi-sync | 1 | yes | push / PR | `cdd-kit validate --openapi` (blocks if `contracts/openapi.json` or `contracts/api/openapi.json` still contain drawer paths) | — |
| nightly-integration | 3 | informational | weekly schedule / dispatch | `pytest tests/integration/ --run-integration-real -m "integration_real or multi_worker" -x` | test report |

### Gate Notes

**response-shape-validate** — The four drawer samples (`get_admin_drawers.json`, `delete_admin_drawers_id.json`, `post_admin_drawers.json`, `put_admin_drawers_id.json`) must be retired from `tests/contract/response-samples.json` and from disk before this gate runs; otherwise the gate validates against removed-endpoint schemas that no longer exist. `get_admin_pages.json` must be regenerated to the slim `{pages:[{route,status}]}` shape and `get_portal_navigation.json` regenerated to the `{statuses:{route:status},…}` shape (no drawers) before the gate runs. See test-plan.md §AC-4 / AC-8.

**unit-mock-integration** — The following test-plan.md rows drive this gate:
- AC-2: `tests/test_page_registry.py` new `TestShrunkStoreBackCompat` + `TestIsApiPublic::test_api_public_key_preserved_after_shrink`.
- AC-3: `tests/test_admin_routes.py` drawer-404 replacements + `PUT /api/pages` field-rejection tests.
- AC-6: `tests/test_page_registry.py` legacy full-CMS back-compat read; missing-file default; `defaultStatus:'dev'` annotation.
- AC-8: `tests/contract/test_schema_coverage.py::test_endpoint_count_at_least_158` pin decremented by 4 (drawer removal).
See test-plan.md §Test Update Contract for deleted tests.

**frontend-unit** — The following test-plan.md rows drive this gate:
- AC-1 / AC-5: `frontend/tests/legacy/portal-shell-navigation.test.js` — `test_manifest_nav_tree_non_admin_matches_baseline`, `test_manifest_nav_tree_admin_matches_baseline`, `test_drawer_order_is_1_through_6`, `test_trace_tools_page_order_is_distinct`, `test_manifest_drawer_ids_use_clean_names`, `test_manifest_excludes_test_drawer`, `test_manifest_display_names_verbatim`, `test_manifest_page_memberships_verbatim`.
- AC-5: `frontend/src/portal-shell/__tests__/navigationManifest.test.js` — `test_all_manifest_routes_exist_in_native_module_registry`, `test_default_status_dev_only_on_admin_dashboard`.
The nav-tree parity assertion must compare the built JS object output of `buildDynamicNavigationState(manifest, statusMap)` against the baseline captured in `current-behavior.md` (drawers, order, display names, visible-page set) for both admin and non-admin roles — a manifest typo yields no backend signal. See test-plan.md §Notes.

**playwright-critical-journeys** — Extends the existing gate command with two new specs:
- `tests/playwright/admin-pages.spec.ts`: admin status-toggle round-trip (`released` → `dev` → persisted); `DrawerManagementPanel` absent from DOM (AC-2, AC-3).
- `tests/playwright/portal-shell-login.spec.ts`: `test_non_admin_sidebar_drawers_match_baseline` — rendered sidebar drawer/page structure matches `current-behavior.md` baseline (AC-1).
The existing gate command list (hold-overview, reject-history, query-tool, eap-alarm) is preserved; these two specs are additions, not replacements.

**openapi-sync** — Blocks merge if either `contracts/openapi.json` or `contracts/api/openapi.json` still contains `GET /admin/api/drawers`, `POST /admin/api/drawers`, `PUT /admin/api/drawers/{drawer_id}`, or `DELETE /admin/api/drawers/{drawer_id}` paths. Both files must be regenerated in the same PR as the backend removal (AC-8). See test-plan.md §AC-4 / AC-8.

## Workflow Changes Applied

No new workflow files and no new gate tiers are required. This change rides existing gates.

**`playwright-critical-journeys` gate command update** (`contract-driven-gates.yml` or equivalent e2e workflow step) — append the two new spec paths:

```yaml
# Before (existing):
- run: cd frontend && npx playwright test tests/playwright/hold-overview.spec.js tests/playwright/reject-history.spec.js tests/playwright/query-tool.spec.js tests/playwright/eap-alarm.spec.js

# After:
- run: cd frontend && npx playwright test tests/playwright/hold-overview.spec.js tests/playwright/reject-history.spec.js tests/playwright/query-tool.spec.js tests/playwright/eap-alarm.spec.js tests/playwright/admin-pages.spec.ts tests/playwright/portal-shell-login.spec.ts
```

No `npx playwright install` step is needed: the test files added here extend existing spec files that already run in CI under the same job, and the Chromium binary is already installed via `~/.cache/ms-playwright/` per CLAUDE.md Hard Rule 2.

All other workflow files (`backend-tests.yml`, `frontend-tests.yml`, `contract-driven-gates.yml`) are unchanged — the existing `unit-mock-integration`, `response-shape-validate`, `frontend-unit`, and `nightly-integration` gate commands auto-discover new and modified test files by path convention.

## Promotion Policy

Standard Tier-2 change promotion:

- All Tier-1 required gates (`response-shape-validate`, `unit-mock-integration`, `frontend-unit`, `playwright-critical-journeys`, `openapi-sync`) must be green.
- Per CLAUDE.md promoted learnings: tasks 6.2 / 6.3 may be marked `done` when Tier-1 passes locally; task 6.4 is `skipped` — no new nightly/weekly gate is defined or modified for this change (the existing `nightly-integration` gate picks up integration tests automatically with no configuration change).
- The `nightly-integration` gate is informational for this change (no new `integration_real` tests added; the existing nightly command is unchanged and already covers the backend).
- PR must not be merged while any Tier-1 gate is red.

## Rollback Policy

1. **Code revert**: `git revert <merge-commit>` restores all removed endpoints (`GET/POST/PUT/DELETE /admin/api/drawers`), the full `set_page_status` signature, the structure-emitting `portal_navigation_config`, `navigationState.js` backend-drawer input, and the admin `DrawerManagementPanel`. No service restart beyond gunicorn reload is required.

2. **`data/page_status.json` self-heal**: A store shrunk to the `{route:status}` map is forward-and-backward safe. The restored `_migrate_navigation_schema` rebuilds the `drawers` array from `DEFAULT_DRAWERS` + `LEGACY_NAV_ASSIGNMENTS` on first post-rollback read and persists it. No manual data repair is required under a normal code-revert rollback.

3. **Exact drawer-id restoration (optional)**: If operators require the pre-change drawer ids verbatim (including renamed `drawer-2`, `drawer`, `drawer-3`), run `git checkout data/page_status.json` after the revert. The self-healed file uses `DEFAULT_DRAWERS` ids, not the renamed ids.

4. **No parquet / Redis / RQ cleanup**: This change touches no spool namespaces, no Redis keys, and no RQ job types. No parquet `rm`, no `redis-cli DEL`, and no worker restart is required as part of rollback.

5. **Contract sample restore**: `get_admin_drawers.json`, `delete_admin_drawers_id.json`, `post_admin_drawers.json`, and `put_admin_drawers_id.json` are tracked in git; they are automatically restored by the code revert. Their entries in `tests/contract/response-samples.json` are likewise restored.

## Merge Eligibility

**Blocked** until all five Tier-1 gates are green:
- `response-shape-validate` (drawer samples retired + pages/navigation samples regenerated)
- `unit-mock-integration` (drawer-404 tests, page_registry shrink + legacy back-compat, `is_api_public` preservation)
- `frontend-unit` (navigationManifest + navigationState nav-tree parity tests for admin AND non-admin vs `current-behavior.md`)
- `playwright-critical-journeys` (admin status-toggle round-trip + drawer-management-absent + portal-shell menu-parity)
- `openapi-sync` (both openapi.json files drawer-path-free)

**Informational risk**: `nightly-integration` is informational; a failure there after merge must be triaged within 1 business day per the CI gate contract Tier-3 policy.
