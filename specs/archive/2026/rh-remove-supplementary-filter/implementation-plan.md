---
change-id: rh-remove-supplementary-filter
schema-version: 0.1.0
last-changed: 2026-06-25
---

# Implementation Plan: rh-remove-supplementary-filter

## Objective
Remove the reject-history supplementary (second-layer) filter section entirely and promote 報廢原因 (LOSSREASONNAME) to the primary Oracle `BASE_WHERE` prefilter layer as a 4th primary-prefilter column, with `reasons[]` forwarded through all three query paths (sync, legacy-async, unified-job) and included in `query_id_input` for cache-key isolation. `workcenter_groups` is fully removed from the reject-history surface.

## Execution Scope

### In Scope
- Backend: add `reasons` param to `_build_base_where()`; remove the supplementary WHERE layer from `_build_where_clause()`; route extraction/forwarding swap (`workcenter_groups` out, `reasons` in); cache + job-service + worker `reasons` plumbing and `query_id_input` inclusion (change-request §Backend scope items 1–5).
- Frontend: remove supplementary panel/props/emits/state/interfaces; add 報廢原因 as 4th primary-prefilter MultiSelect; remove `getAvailableFilters()` and `workcenterGroups` from the DuckDB composable; CSS removal + grid change (change-request §Frontend scope items 6–10).
- Contracts: API (`reasons[]` added / `workcenter_groups` removed), data-shape (`query_id_input` cache-key), business-rule equivalence note, CSS inventory; regen both OpenAPI exports.
- Tests: extend existing files only (no new test files); update stale assertions per test-plan §Test Update Contract.

### Out of Scope
- Any refactor of `paretoSelections`, `DIM_TO_COLUMN`, `queryBatchPareto()` / `queryDetail()` Pareto selection logic beyond removing the `workcenterGroups` param.
- Cross-app `workcenter_groups` surfaces (downtime-analysis, material-consumption, yield-alert, resource) — must remain untouched.
- New endpoints: GET `/api/reject-history/options` already returns `reasons` via `reason_filter_cache.get_reject_reasons()`; do not add an endpoint.
- Any Parquet `_SCHEMA_VERSION` bump or spool purge (none introduced — ci-gates Rollback Policy).
- Stress / soak / monkey / resilience tests (classification: no).

## Required Changes
| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | `services/reject_history_service.py` `_build_base_where()` (281-342) | Add `reasons: Optional[list[str]] = None` kwarg; when non-empty append `NVL(TRIM(r.LOSSREASONNAME), '(未填寫)') IN (:reason_0, …)` with `reason_`-prefixed binds (no collision with `start_date`/`end_date`/`pt_`/`pkg_`/`pf_`); empty/None adds no clause (RHPF-02). NOTE: reason column lives on alias `r` (not `c`) and uses sentinel `'(未填寫)'` (not `'(NA)'`) — confirm alias against the reject_raw CTE before emitting. | backend-engineer |
| IP-2 | `services/reject_history_service.py` `_build_where_clause()` (189-272) | Remove `workcenter_groups`, `packages`, `reasons`, `types` params (supplementary WHERE layer removed); keep only policy flags (includeExcludedScrap, excludeMaterialScrap, excludePbDiode). | backend-engineer |
| IP-3 | `routes/reject_history_routes.py` | Remove `workcenter_groups = _parse_multi_param("workcenter_groups")`; add `reasons = _parse_multi_param("reasons")` with normalize+dedup+sort (same as pj_types/packages/pj_functions); forward `reasons` to `query_id_input`, `execute_primary_query()`, and job_params; remove `workcenter_groups` from all those sites. | backend-engineer |
| IP-4 | `services/reject_dataset_cache.py` `execute_primary_query()` | Add `reasons` kwarg (parity with pj_types/packages/pj_functions); include `reasons` in `query_id_input` dict for cache-key isolation. | backend-engineer |
| IP-5 | `services/reject_query_job_service.py` `execute_reject_query_job()` | Add `reasons` kwarg, normalize, forward to `query_id_input` and `execute_primary_query`. | backend-engineer |
| IP-6 | `workers/reject_history_worker.py` `RejectHistoryJob.pre_query()` (75-176) | Parse `reasons` from job params, include in `query_id_input`, call `_build_base_where(reasons=reasons)`, extract `reason_`-prefixed binds, update each chunk_bind. | backend-engineer |
| IP-7 | `frontend/src/reject-history/components/FilterPanel.vue` | Remove `supplementary-panel` div (303-357), `availableFilters`/`supplementaryFilters` props, `supplementary-change` emit, `emitSupplementary()`, `AvailableFilters`/`SupplementaryFilters` interfaces. Add `primaryReasons?: string[]` + `primaryReasonOptions?: string[]` props, `update:primaryReasons` + `primary-prefilter-close` (reasons) emits, and 報廢原因 MultiSelect as 4th column in `.primary-prefilter-row` (`aria-label="報廢原因 預篩選"`, `data-testid="primary-reason-multiselect"`, `searchable`). | frontend-engineer |
| IP-8 | `frontend/src/core/reject-history-filters.ts` | Add `primaryReasons?: string[]` to `RejectFilterInput` and `RejectFilterSnapshot`; remove any `supplementaryFilters`-related fields. | frontend-engineer |
| IP-9 | `frontend/src/reject-history/App.vue` | Remove `supplementaryFilters` state, `availableFilters` ref, `onSupplementaryChange()`, the `getAvailableFilters()` call. Add `primaryReasons = ref<string[]>([])`; destructure `reasons` in `fetchPrimaryPrefilterOptions()`; prune stale `primaryReasons` in `_schedulePrimaryPrefilterRefresh()`; reset in `resetPrimaryPrefilters()`; include `reasons: primaryReasons.value` in `executePrimaryQuery()` when non-empty; pass `primaryReasons`/`primaryReasonOptions` to FilterPanel. | frontend-engineer |
| IP-10 | `frontend/src/reject-history/useRejectHistoryDuckDB.ts` | Remove `workcenterGroups` param from `queryDetail()` and `queryBatchPareto()` (type params + WHERE clause); remove `getAvailableFilters()` entirely; remove `AvailableFilters` type and `workcenter_groups` from `BatchParetoResult`/related types. Keep `DIM_TO_COLUMN`, `paretoSelections`, Pareto selections unchanged. | frontend-engineer |
| IP-11 | `frontend/src/reject-history/style.css` | Remove `.theme-reject-history .supplementary-panel/.supplementary-header/.supplementary-row/.supplementary-toolbar`; change `.primary-prefilter-row` grid to `repeat(4, minmax(0, 1fr))`; keep mobile `@media (max-width: 768px)` `.primary-prefilter-row { grid-template-columns: 1fr; }`. | frontend-engineer |
| IP-12 | contracts | Record `reasons[]`/`workcenter_groups` request-shape change in `contracts/api/api-contract.md` (+ `api-inventory.md`); regen `contracts/openapi.json` AND `contracts/api/openapi.json`; update `contracts/data/data-shape-contract.md` (`query_id_input` cache-key); confirm BASE_WHERE-vs-supplementary equivalence incl. `(未填寫)` bucket in `contracts/business/business-rules.md`; update `contracts/css/css-inventory.md`; add the four version bumps to `contracts/CHANGELOG.md`. | contract-reviewer |
| IP-13 | tests | Add/update unit, integration, contract, e2e tests per Test Execution Plan; update stale assertions per test-plan §Test Update Contract; run pre-push grep sweep + full pytest. | backend-engineer, frontend-engineer |

## Source Artifact Pointers
| source | relevant pointer | used for |
|---|---|---|
| test-plan.md | AC-1..AC-8 Test Mapping table; Test Update Contract; Notes | tests to run/write, stale-assertion updates, sample regen |
| ci-gates.md | Required Gates table; changelog-versions row (api 1.29.0, data 1.26.0, business 1.31.0, css 1.10.0); Pre-merge local commands | verification commands and gate floor |
| change-classification.md | Required Contracts; Inferred Acceptance Criteria AC-1..AC-8; Tasks Not Applicable | scope of contract edits, AC ownership |
| context-manifest.md | Allowed Paths; Approved Expansions CER-001 | read/write boundary |
| change-request.md | Backend scope 1-5 / Frontend scope 6-10 / Test scope / Pre-push checklist | exact edit sites and signatures |
| contracts/business/business-rules.md | RHPF-02 (empty selection = no clause), RHPF-03 (NULL→sentinel bucket), PH-06 reason semantics | implementation constraint for `(未填寫)` equivalence |

## File-Level Plan
| path or glob | action | notes |
|---|---|---|
| src/mes_dashboard/services/reject_history_service.py | edit | IP-1, IP-2. Confirm `r`/`c` alias for LOSSREASONNAME in the reject_raw CTE. |
| src/mes_dashboard/routes/reject_history_routes.py | edit | IP-3 — swap `workcenter_groups`→`reasons` across query_id_input, execute_primary_query, job_params. |
| src/mes_dashboard/services/reject_dataset_cache.py | edit | IP-4 — `execute_primary_query()` `reasons` kwarg + query_id_input. |
| src/mes_dashboard/services/reject_query_job_service.py | edit | IP-5 — `execute_reject_query_job()` `reasons` kwarg + forwarding. |
| src/mes_dashboard/workers/reject_history_worker.py | edit | IP-6 — `pre_query()` (75-176) reasons parse + binds. |
| src/mes_dashboard/services/reason_filter_cache.py | read only | confirm `get_reject_reasons()` already feeds /options `reasons`; no edit expected. |
| src/mes_dashboard/sql/reject_history/ | read only | confirm reject_raw CTE alias for LOSSREASONNAME; edit only if BASE_WHERE injection point requires it. |
| frontend/src/reject-history/components/FilterPanel.vue | edit | IP-7. |
| frontend/src/core/reject-history-filters.ts | edit | IP-8. |
| frontend/src/reject-history/App.vue | edit | IP-9. |
| frontend/src/reject-history/useRejectHistoryDuckDB.ts | edit | IP-10. |
| frontend/src/reject-history/style.css | edit | IP-11. |
| contracts/api/api-contract.md, api-inventory.md, openapi.json | edit | IP-12 — regen both openapi.json files. |
| contracts/openapi.json | regen | IP-12 — `cdd-kit openapi export --out contracts/openapi.json`. |
| contracts/data/data-shape-contract.md | edit | IP-12 — query_id_input cache-key. |
| contracts/business/business-rules.md | edit | IP-12 — `(未填寫)` bucket equivalence. |
| contracts/css/css-inventory.md | edit | IP-12 — supplementary rules removed, grid change. |
| contracts/CHANGELOG.md | edit | IP-12 — api 1.29.0, data 1.26.0, business 1.31.0, css 1.10.0. |
| tests/test_reject_history_service.py, test_reject_history_routes.py, test_reject_dataset_cache.py, test_reject_query_job_service.py, test_reject_history_async_routes.py, test_reject_history_unified_job.py | edit | IP-13 — extend; per-kwarg `call_args.kwargs[...]`, assert `workcenter_groups` ABSENT. |
| tests/contract/samples/ | regen (scoped) | IP-13 — `pytest tests/contract/test_capture_samples.py` then `git checkout` unaffected samples. |
| frontend/tests/playwright/reject-history-filter.spec.ts, frontend/tests/validation/useRejectHistory.validation.test.js | edit | IP-13. |

## Contract Updates
- API: POST reject-history query endpoints gain `reasons[]` request field, drop `workcenter_groups`; record in `contracts/api/api-contract.md` + `api-inventory.md`; regen `contracts/openapi.json` AND `contracts/api/openapi.json` (changelog api 1.29.0).
- CSS/UI: remove `.supplementary-panel/.supplementary-header/.supplementary-row/.supplementary-toolbar`; `.primary-prefilter-row` → 4-column grid; update `contracts/css/css-inventory.md`; css:check Rule 6 must pass (changelog css 1.10.0).
- Env: none.
- Data shape: `reasons[]` added to `query_id_input` changes cache-key composition; update `contracts/data/data-shape-contract.md` (changelog data 1.26.0).
- Business logic: WHERE-semantics shift (DuckDB post-materialization → Oracle BASE_WHERE `NVL(TRIM(r.LOSSREASONNAME),'(未填寫)')` bucketing); confirm equivalence incl. `(未填寫)` bucket in `contracts/business/business-rules.md` (changelog business 1.31.0).
- CI/CD: none.

## Test Execution Plan
| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-3 (_build_base_where reason_N binds; empty=no clause; (未填寫) verbatim) | tests/test_reject_history_service.py | reason_-prefixed binds; empty list adds no clause; `(未填寫)` present for NULL mapping |
| AC-3 (route forwards reasons[] per-kwarg) | tests/test_reject_history_routes.py | `call_args.kwargs["reasons"]` equals forwarded list |
| AC-5 (workcenter_groups absent from route kwargs) | tests/test_reject_history_routes.py | `"workcenter_groups" not in call_args.kwargs` |
| AC-4 (reasons[] in query_id_input; distinct cache keys) | tests/test_reject_dataset_cache.py | distinct reason selections → distinct cache keys, no bleed |
| AC-4 (reasons[] in job enqueue params) | tests/test_reject_query_job_service.py | `reasons` present in enqueue params |
| AC-4 (legacy-async path) | tests/test_reject_history_async_routes.py | `reasons` forwarded with mock `is_async_available()=True` |
| AC-4 (unified-job path) | tests/test_reject_history_unified_job.py | `reasons` forwarded through unified job |
| AC-7 (BASE_WHERE reasons equivalence incl. (未填寫)) | tests/test_reject_history_service.py | result-set equivalence vs prior supplementary filter |
| AC-6 (Pareto cross-filter / pagination / CSV export) | tests/test_reject_history_routes.py | paretoSelections, pagination contract, CSV streaming preserved |
| AC-1 / AC-2 / AC-5 (composable: no supplementary state; reasons in /options shape; getAvailableFilters not callable) | frontend/tests/validation/useRejectHistory.validation.test.js | assertions pass; css:check passes |
| AC-1 / AC-2 (supplementary panel absent; 4th column present; reasons[] in POST body) | frontend/tests/playwright/reject-history-filter.spec.ts | supplementary markup absent; 報廢原因 column visible; captured POST body contains reasons[] |
| AC-8 (contract samples reflect reasons[]/workcenter_groups) | pytest tests/contract/test_capture_samples.py (then git checkout unaffected) | POST /query sample shape updated |

Required test phases (floor): `collect`, `targeted`, `changed-area`; add `contract` (samples) and `full` (pre-push full-suite grep). Generate evidence with `cdd-kit test run` after `cdd-kit test select rh-remove-supplementary-filter --json`. Full ladder and tier mapping live in test-plan.md and references/sdd-tdd-policy.md.

## Handoff Constraints
- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.
- Pre-push grep sweep is mandatory before gate (test-plan Notes; change-request Pre-push checklist):
  1. `grep -r "workcenter_groups" src/ tests/ frontend/ | grep -v "node_modules\|\.pyc"` — reject-history must NOT appear (only downtime-analysis / material-consumption).
  2. `grep -r "getAvailableFilters" frontend/ | grep -v "node_modules"` — zero results.
  3. `grep -r "supplementary" frontend/src/reject-history/ | grep -v "node_modules"` — zero results.
  4. `cd frontend && npm run css:check` passes.
  5. `cdd-kit openapi export --check --out contracts/openapi.json` passes.
- `cdd-kit gate --strict` runs only the bounded ladder; before pushing, run the FULL pytest suite locally (removing `workcenter_groups` can leave stale assertions in non-bounded files that pass the local gate but fail CI `unit-and-integration-tests`).
- After running the full pytest suite, `git checkout tests/contract/samples/` to drop unrelated sample churn, then re-stage only the reject-history POST /query samples this change altered.

## Known Risks
- Alias/sentinel mismatch: existing `_build_base_where` prefilters use alias `c` and sentinel `'(NA)'`; 報廢原因 (LOSSREASONNAME) lives on alias `r` with sentinel `'(未填寫)'`. Backend-engineer must verify the reject_raw CTE alias before emitting the IN clause — the wrong alias silently drops rows.
- Cache-key boundary: `reasons[]` enters `query_id_input`; the `(未填寫)` bucket plus empty-selection default must not collide with pre-existing cache entries (AC-4 / data-boundary). Verify with tests/test_reject_dataset_cache.py.
- Three-path parity: `reasons[]` must be normalized identically (dedup+sort) in route, cache, job-service, and worker `pre_query`; drift produces different cache keys for the same selection across sync vs async.
- Stale full-tree assertions for `workcenter_groups` outside the bounded ladder — mitigated by the mandatory pre-push grep + full pytest run.
- Both OpenAPI exports must be regenerated; a single-file regen passes the local gate but fails CI `openapi-sync` (CLAUDE.md: regen BOTH `contracts/openapi.json` AND `contracts/api/openapi.json`).
- code-map.yml is fresh (generated 2026-06-25); no staleness risk noted.
