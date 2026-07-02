# Modernization Policy Artifact Notes

Promoted learnings from project history — JSON manifest files that must be kept in sync with page additions/removals.

## Two JSON Files Must Be Updated on Page Add/Remove

**`docs/migration/full-modernization-architecture-blueprint/` contains two files that are NOT reached by grepping Flask routes or Vite config alone:**

1. **`asset_readiness_manifest.json`** — maps route → required dist asset. Read by `app.py:_validate_in_scope_asset_readiness()` at startup via `lru_cache`. Stale entries crash gunicorn with `RuntimeError`.
2. **`route_scope_matrix.json`** — drives in-scope route classification.

Always update both files whenever a change adds or removes a page. Include both in `## Allowed Paths` of the context manifest.

Evidence: `remove-unused-pages` — `/tables` removal not reflected here caused gunicorn startup crash post-deploy.

## data/page_status.json — Manual Entry Deletion Required

**`data/page_status.json` is a runtime-persisted registry that is never modified by code deletion.** `page_registry.py:_load()` reads it at runtime to build navigation drawers. A removed page's entry will continue rendering in the sidebar and emit "缺少 route contract: <route>" until the entry is manually removed from the `pages` array.

Always include `data/page_status.json` in `## Allowed Paths` and delete the page's object from the array as part of any page removal change.

Evidence: `remove-unused-pages` — `/tables` entry persisted in sidebar after all code was deleted.

## drawer_id Change — Update Test Assertion

**When changing a page's `drawer_id` in `data/page_status.json`, also update its corresponding assertion in `tests/test_modernization_policy_hardening.py`.** Each page registration test hardcodes the expected `drawer_id`; the mismatch will not surface at dev time but will fail CI.

The test method is named by convention `test_page_status_contains_<page>_in_<drawer>` — if the drawer changes, rename the method and update the assert.

Evidence: `material-part-consumption` — CI failed after page moved from `drawer-2` to `drawer` without updating the test.

## vite.config.ts INPUT_MAP and routeContracts.js ROUTE_CONTRACTS — Also Required

**`frontend/vite.config.ts`'s `INPUT_MAP`** (page → entry file) must include every new page. Omission makes
`npm run build` silently skip the page; `_validate_in_scope_asset_readiness()` then refuses to boot (missing
dist asset), a hard startup failure.

**`frontend/src/portal-shell/routeContracts.js`'s `ROUTE_CONTRACTS`** (routeId/title/owner/visibilityPolicy/
scope/compatibilityPolicy) must include every new route. Omission does not block boot but emits
"部分導覽項目缺少 route contract" at runtime — a soft failure easy to miss.

No automated test currently asserts either registry's completeness against `navigationManifest.js`'s
registered pages — this exact gap caused two of three post-merge production bugs in `production-achievement-kanban`.

Evidence: `production-achievement-kanban` — new page's INPUT_MAP entry omitted, build silently
skipped it, gunicorn refused to boot; routeContracts.js entry also omitted, runtime nav warning.
