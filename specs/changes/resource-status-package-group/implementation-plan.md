---
change-id: resource-status-package-group
schema-version: 0.1.0
last-changed: 2026-05-21
---

# Implementation Plan: resource-status-package-group

## Objective

Add Package Group (`PACKAGEGROUPNAME`) to the resource-status page (`/portal-shell/resource`) end-to-end:
- Backend resolves `PACKAGEGROUPID` (already cached in `resource_cache`) → `PACKAGEGROUPNAME` via a 46-row in-process lookup dict (`DW_MES_RESOURCE_PACKAGEGROUP`, 7-day TTL, independent of the 24h resource_cache cycle).
- `/api/resource/status` returns `PACKAGEGROUPNAME: string | null` per record.
- `/api/resource/status`, `/status/summary`, `/status/matrix` accept an optional `package_groups` filter param.
- `/api/resource/status/options` returns a `package_groups: string[]` list.
- Frontend: FilterBar gains a Package Group MultiSelect; EquipmentCard shows a Package text row (hidden when null); MatrixSection gains Package as an expandable dimension.

Contracts are already updated and authoritative — see Source Artifact Pointers. Do not re-edit contracts except where this plan explicitly requires.

## Execution Scope

### In Scope
- `resource_cache.py`: package-group lookup dict, 7-day TTL refresh, `get_package_group_name()`, `get_package_groups()`.
- `resource_service.py`: `package_groups` filter + `PACKAGEGROUPNAME` field in `get_merged_resource_status()`; forward through `get_resource_status_summary()` and `get_workcenter_status_matrix()`; add `package_groups` to `query_resource_filter_options()`.
- `resource_routes.py`: parse + forward `package_groups` on `/status`, `/status/summary`, `/status/matrix`; expose `package_groups` on `/status/options`.
- Frontend `resource-status/`: FilterBar (Package Group MultiSelect), EquipmentCard (Package text row, hide on null), MatrixSection (Package dimension), App.vue (wiring of param, options prop, field passthrough).
- Backend + frontend tests per test-plan.md (TDD: write failing tests first).

### Out of Scope (do not implement)
- Cross-filter narrowing between Package Group and other filter dimensions (non-goal; see Known Risks for the does_not_narrow decision).
- Any KPI changes — OU% / AVAIL% must remain identical (explicitly excluded; AC-3).
- Other pages: resource-history, dashboard, etc.
- New Redis keys, new spool files, DB migrations.
- New CSS source file or `css-inventory.md` edits (css-contract.md confirms none needed).
- Edits to `data/page_status.json`, `asset_readiness_manifest.json`, `route_scope_matrix.json` (no route added/removed).

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | `resource_cache.py` | Add module-level `_package_group_lookup: dict[str, str]`, `_package_group_refreshed_at: float = 0.0`, `_PACKAGE_GROUP_SYNC_INTERVAL = 604800`. | backend-engineer |
| IP-2 | `resource_cache.py` | Add `_load_package_group_lookup()` — query `DWH.DW_MES_RESOURCE_PACKAGEGROUP` via `read_sql_df`, build `{str(pgid).strip(): pgname}`; on failure leave dict unchanged / empty and log (no raise). Set `_package_group_refreshed_at = time.time()` on success. | backend-engineer |
| IP-3 | `resource_cache.py` | Add `get_package_group_name(pgid: str \| None) -> str \| None` — return None when pgid is None/NaN/empty; trigger `_load_package_group_lookup()` if `time.time() - _package_group_refreshed_at > _PACKAGE_GROUP_SYNC_INTERVAL`; resolve via `_package_group_lookup.get(str(pgid).strip())`; return None on miss. | backend-engineer |
| IP-4 | `resource_cache.py` | Add `get_package_groups() -> list[str]` — sorted distinct `PACKAGEGROUPNAME` values from the lookup dict (trigger TTL reload if expired). | backend-engineer |
| IP-5 | `resource_cache.py` | In `refresh_cache()` (the 24h sync entry; lines ~699-742), call `_load_package_group_lookup()` only if its own 7-day TTL has expired; the package-group timer must NOT reset on a 24h resource sync. (TTL independence — AC-6.) | backend-engineer |
| IP-6 | `resource_service.py::get_merged_resource_status()` | Add `package_groups: Optional[List[str]] = None` param. Resolve `pgname = get_package_group_name(resource.get('PACKAGEGROUPID'))`; add `'PACKAGEGROUPNAME': pgname` to the merged record dict. Apply filter: `if package_groups and pgname not in package_groups: continue` (null pgname excluded when filter active). Filter logic must sit alongside the existing `families` / `resource_ids` checks so it applies on BOTH the warm-cache and Oracle-fallback resource sources (both flow through `get_all_resources()`). | backend-engineer |
| IP-7 | `resource_service.py` | `get_resource_status_summary()` and `get_workcenter_status_matrix()`: add `package_groups: Optional[List[str]] = None` and forward to `get_merged_resource_status(package_groups=package_groups)`. Do not alter OU%/AVAIL%/matrix count math. | backend-engineer |
| IP-8 | `resource_service.py::query_resource_filter_options()` | Add `'package_groups': get_package_groups()` to the returned dict (import `get_package_groups` from `resource_cache`). | backend-engineer |
| IP-9 | `resource_routes.py` | `/status`, `/status/summary`, `/status/matrix`: parse `package_groups_param = request.args.get('package_groups')`; `package_groups = package_groups_param.split(',') if package_groups_param else None`; forward `package_groups=package_groups` to the corresponding service call. | backend-engineer |
| IP-10 | `resource_routes.py::api_resource_status_options()` | Add `'package_groups': get_package_groups()` to the inline `data` dict (this handler builds its own dict and does NOT call `query_resource_filter_options()` — see Known Risks R-1). Import `get_package_groups` from `resource_cache`. This is the list the frontend `loadOptions()` consumes. | backend-engineer |
| IP-11 | `FilterBar.vue` | Add `packageGroups?: string[]` prop and `selectedPackageGroups?: string[]` prop; add a `change-package-groups: [groups: string[]]` emit; render a `<MultiSelect>` block (placeholder e.g. "全部 Package") reusing `shared-ui/components/MultiSelect.vue`. Prop/emit additions must be additive. | frontend-engineer |
| IP-12 | `EquipmentCard.vue` | Add `PACKAGEGROUPNAME: string \| null` to the `EquipmentItem` interface; render a text row `<span class="eq-info-item"><span class="label">Package</span><span class="value">{{ equipment.PACKAGEGROUPNAME }}</span></span>` inside `.eq-info`, guarded by `v-if="equipment.PACKAGEGROUPNAME"` (truthy check — hides null AND empty string). | frontend-engineer |
| IP-13 | `MatrixSection.vue` | Add Package as an expandable dimension in the matrix hierarchy following the existing workcenter→family→resource pattern (extend `EquipmentItem` with `PACKAGEGROUPNAME`). Must not change OU%/total/status count math (AC-3). | frontend-engineer |
| IP-14 | `App.vue` | Extend `EquipmentItem` + `ResourceOption`/options handling: add `packageGroups` ref populated from `/status/options` `data.package_groups`; add `packageGroups` to filter orchestrator state + `buildFilterParams()` (`params.package_groups = filterState.packageGroups.join(',')` when non-empty); pass `:package-groups` and `:selected-package-groups` to FilterBar and wire `@change-package-groups`; pass `PACKAGEGROUPNAME` through `allEquipment` to EquipmentCard/MatrixSection (already flows since records are spread). | frontend-engineer |
| IP-15 | `frontend/src/resource-status/style.css` | Only if any new authored CSS is required (e.g. `.ui-card` overflow override for the new MultiSelect dropdown). All rules MUST be scoped under `.theme-resource`. Prefer reusing existing classes — css-contract.md states no new class names are required unless existing ones cannot cover the surface. | frontend-engineer |
| IP-16 | backend tests | Write failing tests first per test-plan.md §Backend Unit Tests, then implement. Use `mock.call_args.kwargs['package_groups']` for forwarding (NOT `assert_called_once_with`). Test both warm-cache and Oracle-fallback paths. | backend-engineer |
| IP-17 | frontend tests | Write/extend `frontend/tests/legacy/resource-status.test.js` per test-plan.md §Frontend Unit Tests. | frontend-engineer |

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| change-classification.md | Inferred Acceptance Criteria AC-1..AC-7 | acceptance scope; agent ownership |
| test-plan.md | Acceptance Criteria → Test Mapping; §Backend/Frontend Unit Tests; §Notes | exact test names, TDD discipline, both-path requirement |
| ci-gates.md | Required Gates table; Merge Eligibility Decision | verification commands and merge bar |
| contracts/api/api-contract.md | §Resource-Status Package Group (lines 304-313); endpoint table rows 107-110 | param + response field shape; `/status/options` is the options surface |
| contracts/data/data-shape-contract.md | §3.10 (field table line 584; NULL semantics §3.10.2; filter semantics §3.10.3) | `PACKAGEGROUPNAME` nullable contract; CHAR `str().strip()` rule; filter exclusion rule |
| contracts/css/css-contract.md | §Resource-Status UI Surface Rules (lines 111-121); §Known Global Rule Interactions | `.theme-resource` scoping; MultiSelect-in-`.ui-card` overflow pattern; hide-on-null rule |
| CLAUDE.md | Test Coverage Discipline; Shared UI Component Notes (MultiSelect additive); Accessibility Notes | route per-kwarg assertion; both-path tests; MultiSelect additive-only; focus-return on close |

## File-Level Plan

| path or glob | action | notes |
|---|---|---|
| `src/mes_dashboard/services/resource_cache.py` | edit | IP-1..IP-5 lookup dict + TTL + 3 new functions. Use `read_sql_df` (already imported). |
| `src/mes_dashboard/services/resource_service.py` | edit | IP-6..IP-8. Import `get_package_group_name`, `get_package_groups` from `resource_cache`. |
| `src/mes_dashboard/routes/resource_routes.py` | edit | IP-9, IP-10. Add `get_package_groups` to the existing `resource_cache` import block (lines 121-124). |
| `frontend/src/resource-status/components/FilterBar.vue` | edit | IP-11. |
| `frontend/src/resource-status/components/EquipmentCard.vue` | edit | IP-12. |
| `frontend/src/resource-status/components/MatrixSection.vue` | edit | IP-13. |
| `frontend/src/resource-status/App.vue` | edit | IP-14. |
| `frontend/src/resource-status/style.css` | edit (conditional) | IP-15 — only if new CSS needed; all rules under `.theme-resource`. |
| `tests/test_resource_cache.py` | edit/add | IP-16 — `TestPackageGroupLookup` cases per test-plan.md. |
| `tests/test_resource_service.py` | edit/add | IP-16 — `TestGetMergedResourceStatus` + `TestQueryResourceFilterOptions` cases. |
| `tests/test_resource_routes.py` | edit/add | IP-16 — route forwarding + options field cases. |
| `frontend/tests/legacy/resource-status.test.js` | edit/add | IP-17 — EquipmentCard / FilterBar / MatrixSection cases. |
| `frontend/dist/**` (via `npm run build`) | regenerate | After CSS/SFC edits, run `cd frontend && npm run build` (CLAUDE.md: app serves from `static/dist/`). |

Note: `frontend/src/resource-shared/components/HierarchyTable.vue` is consumed by MatrixSection; only edit it if the Package dimension cannot be expressed via the existing `columns`/`hierarchy` props (it is shared — keep any change additive). Prefer extending the hierarchy build in MatrixSection.vue.

## Contract Updates

All contracts are ALREADY updated by contract-reviewer and are authoritative — implementation agents MUST conform to them and MUST NOT re-edit unless an implementation detail contradicts them (then stop and report `blocked`).

- API: done — `contracts/api/api-contract.md` §Resource-Status Package Group + endpoint rows 107-110 + CHANGELOG api 1.10.0. Conform.
- CSS/UI: done — `contracts/css/css-contract.md` §Resource-Status UI Surface Rules + CHANGELOG css 1.4.0. Scope under `.theme-resource`; no new CSS source file; no `css-inventory.md` edit.
- Env: n/a.
- Data shape: done — `contracts/data/data-shape-contract.md` §3.10 + CHANGELOG data 1.9.0. Conform `PACKAGEGROUPNAME` nullable + filter semantics.
- Business logic: n/a (no KPI/calc change; non-goal preserved).
- CI/CD: n/a (no new gate; existing gates apply).

## Test Execution Plan

Run backend tests inside conda env (`conda run -n mes-dashboard pytest ...`). TDD: write failing tests first, then implement.

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 (filter narrows list/matrix) | `tests/test_resource_service.py::TestGetMergedResourceStatus::test_package_groups_filter_warm_cache_path` and `..._oracle_fallback_path`; frontend `FilterBar emits package_groups filter on MultiSelect change` | filtered records exclude non-matching package groups on both paths |
| AC-2 (card row, hide on null/empty) | `frontend/tests/legacy/resource-status.test.js`: `EquipmentCard shows/hides PACKAGEGROUPNAME row` (present / null / empty string) | row renders only when truthy |
| AC-3 (Matrix Package dim, KPI unchanged) | `MatrixSection renders Package dimension column`; `MatrixSection Package dimension does not alter OU% or AVAIL% values` | Package dimension present; OU%/AVAIL% unchanged |
| AC-4 (options list + route forwarding) | `tests/test_resource_routes.py::test_resource_status_forwards_package_groups_kwarg`, `..._non_default_value_forwarded`, `test_resource_filter_options_returns_package_groups_field`; `tests/test_resource_service.py::TestQueryResourceFilterOptions::*` | `mock.call_args.kwargs['package_groups'] == ['PKG-A']`; options dict contains `package_groups` |
| AC-5 (PGID→PGNAME, CHAR key) | `tests/test_resource_cache.py::TestPackageGroupLookup::test_char_key_trailing_space_stripped_on_build` / `..._on_resolve` / `test_null_packagegroupid_resolves_to_none` / `test_unknown_packagegroupid_resolves_to_none`; `tests/test_resource_service.py::TestGetMergedResourceStatus::test_packagegroupname_added_when_packagegroupid_present` / `..._is_none_when_packagegroupid_null` | `'P01 '` resolves same as `'P01'`; null/unknown → None |
| AC-6 (7-day TTL independence) | `tests/test_resource_cache.py::TestPackageGroupLookup::test_lookup_ttl_is_7_days_independent_of_resource_cache`, `test_builds_lookup_dict_from_oracle_rows` | refresh timer stored separately from 24h resource-cache timestamp |
| AC-7 (contracts pass) | `pytest tests/test_api_contract.py tests/test_data_shape_contract.py`; `cdd-kit validate` | contract tests green |
| gate bar | ci-gates.md Required Gates: `pytest tests/test_resource_cache.py tests/test_resource_service.py tests/test_resource_routes.py -x --tb=short`; `cd frontend && npm run test`; `cd frontend && npm run css:check`; `ruff check .`; `cdd-kit validate` | all Tier 0/1 required gates green |

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.
- `MultiSelect.vue` is shared by 12 feature apps (CLAUDE.md) — do NOT modify it; the new Package Group filter must consume it as-is with existing props/emits.
- All new CSS scoped under `.theme-resource`; must pass `npm run css:check` Rule 6.
- After frontend source edits, run `cd frontend && npm run build` (app serves from `static/dist/`).

## Known Risks

- R-1 (options-surface discrepancy): The task brief said add `package_groups` to `query_resource_filter_options()`, but the API contract (line 308) and the frontend (`App.vue::loadOptions()` reads `/api/resource/status/options`) make `/status/options` the authoritative options surface. `/status/options` is served by `resource_routes.py::api_resource_status_options()` which builds its own inline dict and does NOT call `query_resource_filter_options()`. Therefore IP-10 (route inline dict) is the contract-critical path the frontend consumes; IP-8 (`query_resource_filter_options()`) is also done to satisfy test-plan row `TestQueryResourceFilterOptions::*` and `/filter_options`. Implement BOTH. If contract-reviewer intended only one surface, stop and reconcile before merging.
- R-2 (cross-filter scope): Cross-filter narrowing is a non-goal. The existing FilterBar family/machine cascade is computed client-side in App.vue from `allResources`; the new Package Group filter is server-side only. If resource-status does not currently cross-filter package group against other dimensions, add a "does_not_narrow" pin test only if the page already cross-filters server-side (per CLAUDE.md / test-plan.md §Out of Scope). Confirm before adding.
- R-3 (TTL timer reset): IP-5 must keep the package-group 7-day timer independent of the 24h resource sync. A naive call to `_load_package_group_lookup()` on every `refresh_cache()` would reset the 7-day timer to a 24h cadence and violate AC-6. The TTL guard (`time.time() - _package_group_refreshed_at > _PACKAGE_GROUP_SYNC_INTERVAL`) must wrap the call.
- R-4 (CHAR padding): `PACKAGEGROUPID` is Oracle CHAR. `str(pgid).strip()` MUST be applied on BOTH dict build and lookup, or 91%-populated keys silently miss. Covered by AC-5 tests; do not skip the trailing-space fixtures.
- R-5 (graceful degradation): A lookup-dict load failure must yield `PACKAGEGROUPNAME = null` for all records, never a 500 (data-shape §3.10.2). `get_package_group_name()` must swallow/log load errors and return None.
- R-6 (`MatrixSection` Package dimension must not alter KPI math): the Package dimension may only add hierarchy/columns; OU%/AVAIL%/status counts must be byte-identical (AC-3). Pin with the explicit no-KPI-change frontend test.
