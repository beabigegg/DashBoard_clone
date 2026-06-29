---
change-id: msd-type-package-filter
schema-version: 0.1.0
last-changed: 2026-06-29
---

# Implementation Plan: msd-type-package-filter

## Objective
Add Type (`PJ_TYPE`) and Package (`PRODUCTLINENAME`) filter dimensions to mid-section-defect:
a new cache-backed `container-filter-options` endpoint, two new `pj_types[]`/`packages[]`
params on the analysis endpoint applied as a Python post-query filter on `detection_df`,
and two cross-filtered FilterBar MultiSelects. Reuse the existing `container_filter_cache`;
no Oracle SQL change. Acceptance criteria AC-1..AC-7 (change-classification.md §Inferred AC).

## Execution Scope

### In Scope
- Backend: new route + reuse of `container_filter_cache.get_filter_options()`; thread
  `pj_types`/`packages` route → `query_analysis` → `resolve_analysis_trace_context`; post-query
  filter on `detection_df`; include the two params in the analysis result cache keys.
- Contracts: api-contract, api-inventory, data-shape, CHANGELOG, dual openapi.json regen,
  one targeted contract sample (contract-reviewer.yml blocking-items; D-CR-01).
- Frontend: App.vue `pjTypes`/`packages` state, FilterBar two MultiSelects, new
  `useContainerFilterOptions` composable mirroring `useFirstTierFilters`.
- Tests: extend existing files only (test-plan.md §AC→Test Mapping).

### Out of Scope (Non-goals)
- No Oracle SQL / `station_detection.sql` change (filter is Python-only on `detection_df`).
- No PJ_BOP / PJ_FUNCTION filters (not output by station_detection.sql).
- No new Redis cache namespace or new key for filter-options; reuse 24h-TTL path (AC-6).
- No new CSS source file (MultiSelect.vue is shared, used as-is — confirm css-contract §4 scope).
- No refactor of the MSD trace/spool pipeline or `msd_duckdb_runtime` internals.
- No new env var, feature flag, nightly/weekly gate (ci-gates.md §Nightly/Weekly).

## Required Changes
| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | backend route | Add `GET /api/mid-section-defect/container-filter-options`; parse `selected` JSON, call `container_filter_cache.get_filter_options(selected)`, return `data={pj_types,packages,bops,pj_functions}` + `meta={updated_at,schema_version}`; 400 on malformed JSON; mirror production-history route 101-148 | backend-engineer |
| IP-2 | backend service+route | Thread `pj_types`/`packages` (multi-value) through `api_analysis` → `query_analysis` → `resolve_analysis_trace_context`; apply filter inside `resolve_analysis_trace_context` (see Constraints C-2); add both to `_analysis_cache_key` (route) AND `make_cache_key` filters (service) — Constraint C-1 | backend-engineer |
| IP-3 | contracts | Edit api-contract.md (endpoint row + analysis row + `MsdContainerFilterOptionsResponse` schema), api-inventory.md (mid_section_defect_routes row), data-shape-contract.md §2.13, CHANGELOG.md `[api 1.32.0]`+`[data 1.28.0]` | backend-engineer |
| IP-4 | contracts export | Regen BOTH `contracts/openapi.json` and `contracts/api/openapi.json` via `cdd-kit openapi export`; add `tests/contract/response-samples.json` entry; targeted sample capture for `get_mid_section_defect_container_filter_options` only | backend-engineer |
| IP-5 | frontend state | Add `pjTypes`/`packages` to `filters` reactive, `committedFilters`, `CommittedFilters` + `SessionCache.filters` interfaces, `snapshotFilters`; emit in `buildFilterParams` when non-empty | frontend-engineer |
| IP-6 | frontend FilterBar | Add Type + Package MultiSelect controls with `data-testid`; new props for options; `updateFilters({ pjTypes/packages })` | frontend-engineer |
| IP-7 | frontend composable | New `useContainerFilterOptions` (mirror `useFirstTierFilters`): fetch on mount + on selection change, 200ms debounce, cross-filter narrowing both directions | frontend-engineer |
| IP-8 | backend tests | Extend `tests/test_mid_section_defect_routes.py` + `tests/test_mid_section_defect_service.py` + contract capture per test-plan rows | backend-engineer |
| IP-9 | frontend tests | Extend `mid-section-defect-composables.test.js` + `mid-section-defect.spec.ts`; update `installBaseRoutes` mock (test-plan §Test Update Contract) | frontend-engineer |

## Source Artifact Pointers
| source | relevant pointer | used for |
|---|---|---|
| test-plan.md | §AC→Test Mapping; §Data-Boundary 1-14; §Test Update Contract | tests to write/extend, mock update |
| ci-gates.md | §Required Gates (5 gates); §Workflow (e2e step) | verification commands, openapi dual-export |
| change-classification.md | §Inferred AC AC-1..AC-7; §Tasks Not Applicable | scope + acceptance |
| agent-log/contract-reviewer.yml | blocking-items; D-CR-01; version-bumps | contract edits + meta placement |
| contracts/api/api-contract.md | §Schemas, §Schema Authoring Rules | new schema authoring + dual openapi regen |
| container_filter_cache.py | `get_filter_options` 139-220; `SCHEMA_VERSION` 55 | endpoint payload shape (no Oracle) |
| production_history_routes.py | `api_production_history_filter_options` 101-148 | route template + meta wrapper |
| mid_section_defect_service.py | `resolve_analysis_trace_context` 172-222; `query_analysis` 325-413 | filter insertion + cache key |
| frontend useFirstTierFilters.ts | `useFirstTierFilters` 109-355; `DEFAULT_DEBOUNCE_MS` 98 | composable cross-filter pattern |

## File-Level Plan
| path | action | notes |
|---|---|---|
| src/mes_dashboard/routes/mid_section_defect_routes.py | edit | New route fn near `api_station_options` (104-106); extend `api_analysis` (109-150) + `_parse_common_params` (58-67) + `_analysis_cache_key` (70-87) |
| src/mes_dashboard/services/mid_section_defect_service.py | edit | Add params to `resolve_analysis_trace_context` (172) + `query_analysis` (325); filter `detection_df` after line 185 (before line 187); extend `make_cache_key` (357-366) |
| src/mes_dashboard/services/container_filter_cache.py | read-only | Reuse `get_filter_options`; do NOT modify |
| contracts/api/api-contract.md, api-inventory.md, data/data-shape-contract.md, CHANGELOG.md | edit | IP-3 |
| contracts/api/openapi.json, contracts/openapi.json | regen | IP-4 (`cdd-kit openapi export`) |
| tests/contract/response-samples.json + samples/get_mid_section_defect_container_filter_options.json | add | targeted capture only |
| frontend/src/mid-section-defect/App.vue | edit | IP-5 (filters 218-230, committedFilters 231-237, buildFilterParams 496-514, snapshotFilters 541-552, interfaces) |
| frontend/src/mid-section-defect/components/FilterBar.vue | edit | IP-6 (after loss-reasons block 163-174) |
| frontend/src/mid-section-defect/composables/useContainerFilterOptions.ts | add | IP-7 (new dir; mirror useFirstTierFilters) |
| tests/test_mid_section_defect_routes.py, tests/test_mid_section_defect_service.py | edit | IP-8 |
| frontend/tests/legacy/mid-section-defect-composables.test.js, frontend/tests/playwright/mid-section-defect.spec.ts | edit | IP-9 |

## Contract Updates
- API: new `GET /api/mid-section-defect/container-filter-options` row + analysis row (`pj_types[]`,
  `packages[]` optional); `MsdContainerFilterOptionsResponse` schema (api-contract §Schemas, authoring rules).
  api-inventory mid_section_defect_routes row. Versions: api 1.31.0→1.32.0, api-inventory 1.2.8→1.2.9.
- CSS/UI: none expected (shared MultiSelect, no authored CSS). If any `.theme-*` source is added,
  update css-inventory + css-contract and run `css:check` (css-contract Rule 6).
- Env: none.
- Data shape: data-shape §2.13 (filter-options shape; `updated_at`/`schema_version` in meta, mirrors §2.7;
  analysis response shape stable under filtering). Version data 1.27.0→1.28.0.
- Business logic: none.
- CI/CD: one e2e step added to `frontend-tests.yml` (ci-gates.md §Workflow); no new workflow/secret.

## Test Execution Plan
| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | tests/test_mid_section_defect_routes.py::test_container_filter_options_returns_type_and_package_lists | data has pj_types/packages |
| AC-1/AC-6 | tests/test_mid_section_defect_routes.py::test_container_filter_options_does_not_call_read_sql_df | `read_sql_df` not called |
| AC-2 | tests/test_mid_section_defect_service.py::test_query_analysis_filter_by_pj_type_reduces_rows | filtered seed < unfiltered |
| AC-2 | tests/test_mid_section_defect_service.py::test_query_analysis_filter_pj_type_and_package_and_semantics | AND-narrowing |
| AC-2 | tests/test_mid_section_defect_routes.py::test_analysis_forwards_pj_types_kwarg | `call_args.kwargs['pj_types']` (per-kwarg) |
| AC-5 | tests/test_mid_section_defect_service.py::test_query_analysis_no_pj_types_packages_output_unchanged | parity vs baseline |
| AC-7 | tests/test_mid_section_defect_service.py::test_query_analysis_null_pj_type_column_no_crash | NaN excluded, no 5xx |
| AC-3/AC-4 | frontend/tests/legacy/mid-section-defect-composables.test.js (state + cross-filter rows) | state incl pjTypes/packages; Type narrows Package |
| AC-3/AC-4 | frontend/tests/playwright/mid-section-defect.spec.ts (render + narrow rows) | both selects render; Type narrows Package |

Full AC→test list and 14 data-boundary cases: test-plan.md (do not duplicate here).

Ladder phases required: `collect`, `targeted`, `changed-area` (floor). Add `contract` (new endpoint +
params). Implementation agents generate evidence via `cdd-kit test run`; the gate validates
`test-evidence.yml`. Required PR gates: ci-gates.md §Required Gates.

## Constraints
- C-1 (cache-collision, critical): The analysis result cache keys do NOT currently include
  `pj_types`/`packages` — `_analysis_cache_key` (route 70-87) and `make_cache_key` (service 357-366) key on
  `{start_date,end_date,loss_reasons,station,direction}` only. You MUST add `pj_types`/`packages` to BOTH,
  or a filtered query collides with an unfiltered one and returns the cached unfiltered result (breaks
  AC-2/AC-5). Adding dict entries keeps the key *structure* unchanged (honors change-request §Constraints).
- C-2 (filter insertion point): Apply the `pj_types`/`packages` filter to `detection_df` inside
  `resolve_analysis_trace_context`, immediately after `_fetch_station_detection_data` returns (after line 185,
  BEFORE `available_loss_reasons` 187 and seed/`trace_query_id` derivation 192-211). This narrows
  `seed_container_ids` so `trace_query_id` and the spool/async job reflect the filtered set. Filtering later in
  `query_analysis` (after line 370) is ineffective — the summary is served from the spool by `trace_query_id`,
  not from `detection_df`.
- C-3: AND-semantics; empty/absent list = no restriction (AC-5/AC-7 #1,#5,#6). Use pandas membership
  (`.isin`) so NULL `PJ_TYPE`/`PRODUCTLINENAME` are excluded from matches (AC-7 #8,#9); duplicate param
  values collapse (#10). Malformed multi-value param → graceful empty/no filter, never 5xx (#13).
- C-4: Route forwarding tests use `call_args.kwargs[key]` per-kwarg, not `assert_called_once_with` (CLAUDE.md
  test-discipline; test-plan §Notes).
- C-5: Regenerate BOTH openapi exports after any api-contract endpoint/schema/version edit; `openapi-sync`
  gate fails otherwise. Contract sample capture is targeted — `git checkout tests/contract/samples/` to drop
  unrelated churn before staging (test-plan §Notes).
- C-6: Playwright `installBaseRoutes` must register the `container-filter-options` mock BEFORE specific
  overrides (LIFO rule; ci-workflow). Stage only this change's `specs/changes/` dir (pre-commit hook scope).
- C-7: `container_filter_cache.get_filter_options` already fail-opens on unknown/empty selections and Redis
  miss; do NOT add a second Oracle path in the route (AC-6; data-boundary #11,#12).

## Handoff Constraints
- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan; CER-001 (`msd_duckdb_runtime.py`) is pending and NOT required —
  the filter insertion point (C-2) is fully determined by `resolve_analysis_trace_context`; do not edit the
  runtime. Need other paths → file a Context Expansion Request and stop.

## Known Risks
- R-1: C-1 cache-collision is the highest-risk item; the upstream "cache key unchanged" note refers to the
  container_filter_cache Redis structure, not the analysis result cache. AC-2/AC-5 tests are the tripwire.
- R-2: C-2 assumes `make_trace_query_id` (trace_job_service, outside read scope) hashes `container_ids` so a
  narrowed seed yields a distinct `trace_query_id`. C-1 guarantees top-level correctness regardless; verify
  the spool-key behavior during implementation if filtered/unfiltered ever share a `trace_query_id`.
- R-3: `detection_df` must contain `PJ_TYPE` and `PRODUCTLINENAME` columns (change-request assumption,
  confirmed by classification §Clarifications). If absent for some station, filter must no-op gracefully.
