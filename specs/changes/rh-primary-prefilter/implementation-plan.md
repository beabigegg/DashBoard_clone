---
change-id: rh-primary-prefilter
schema-version: 0.1.0
last-changed: 2026-06-25
---

# Implementation Plan: rh-primary-prefilter

> STATUS: blocked — execution gated on CER-1..CER-5 approval.
> The parity-critical injection point (`reject_dataset_cache.execute_primary_query`
> / `_make_query_id` / `_execute_and_spool`) and both async job paths live outside
> the current `## Allowed Paths`. IP-2, IP-3, IP-9, IP-10 below cannot be executed
> until the user approves the Context Expansion Requests via
> `cdd-kit context approve rh-primary-prefilter CER-1` (and CER-2..CER-5).
> Do not begin those IPs while their CER is `pending`. IP-1, IP-4..IP-8, IP-11..IP-14
> are inside current allowed paths and may proceed.

## Objective

Add three optional primary-query prefilters — `pj_types[]`, `packages[]`,
`pj_functions[]` — to `POST /api/reject-history/query`, injected into the Oracle
`{{ BASE_WHERE }}` slot (inside the `reject_raw` CTE, before GROUP BY) as
`NVL(TRIM(c.PJ_TYPE|PRODUCTLINENAME|PJ_FUNCTION), '(NA)') IN (...)`. Values must
flow identically through the sync path, both async/RQ paths, and the
cache/spool key. Empty/absent selection must be equivalent to current behavior.
Three matching MultiSelects render in the FilterPanel primary section, sourced
from the existing cross-filter options API.

## Execution Scope

### In Scope
- Backend service: a new BASE_WHERE builder that renders the three prefilters as
  `NVL(TRIM(c.X), '(NA)') IN (...)` plus bind params, threaded into
  `_prepare_sql(..., base_where=...)`.
- Backend route: extract `pj_types` / `packages` / `pj_functions` from the JSON
  body of `api_reject_history_query`; include them in `_query_id_input` (cache
  key) and `job_params` (both async paths); silently ignore `pj_bop`.
- Backend dataset/cache + job layers (CER-gated): thread the three fields through
  `execute_primary_query`, `_make_query_id`, `_execute_and_spool` (spool key),
  the legacy `execute_reject_query_job`, and the unified `reject_history_worker`.
- API/data/business contracts: three new optional request params; regenerate BOTH
  `contracts/openapi.json` and `contracts/api/openapi.json`.
- Frontend: three MultiSelects in FilterPanel primary section; reactive state in
  App.vue; new fields in `RejectFilterInput`/snapshot; include in primary query
  payload; options from the existing production-history filter-options API.
- Tests per `test-plan.md` Test Names section.

### Out of Scope
- `PJ_BOP` in any form — no param, no SQL clause, no UI control (AC-6). Only the
  verified-absent test is in scope.
- Any change to `performance_daily_lot.sql` template — the `{{ BASE_WHERE }}` slot
  already exists (line 70). Do not add new placeholders.
- Supplementary / DuckDB filter logic (`_apply_supplementary_filters`,
  `apply_view`) — unchanged. The existing supplementary `packages` field in
  `reject-history-filters.ts` is a DIFFERENT layer; do not merge the two.
- `container_filter_cache` producer and the production-history filter-options
  endpoint — read/consume only; no edits.
- Oracle index / schema work; spool namespace or schema-version bump.
- `_build_where_clause` (WHERE_CLAUSE) semantics; new prefilters go to BASE_WHERE only.

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | service: `reject_history_service.py` | Add `_build_base_where(start_date, end_date, pj_types, packages, pj_functions)` -> `(base_where_str, params_dict)`. Always include the date predicate (`_DEFAULT_BASE_WHERE` equivalent); append `NVL(TRIM(c.PJ_TYPE), '(NA)') IN (...)`, `NVL(TRIM(c.PRODUCTLINENAME), '(NA)') IN (...)`, `NVL(TRIM(c.PJ_FUNCTION), '(NA)') IN (...)` for non-empty lists. Use `QueryBuilder` for IN binds (distinct param names; no collision with `:start_date`/`:end_date` or WHERE_CLAUSE binds). | backend-engineer |
| IP-2 | dataset/cache: `reject_dataset_cache.py` (CER-1) | In `execute_primary_query` (804-1233) / `_execute_and_spool` (481-796): accept the three lists, call `_build_base_where(...)`, pass result via `_prepare_sql(..., base_where=...)`, merge its binds into the executed params dict. | backend-engineer |
| IP-3 | cache key: `reject_dataset_cache._make_query_id` (CER-1) | Add the three normalized lists to the query-id input AND the spool key so distinct prefilters give distinct entries; empty/absent normalize identically to today's key (RHPF-05). | backend-engineer |
| IP-4 | route: `reject_history_routes.py` | In `api_reject_history_query` (641-793): parse `pj_types`/`packages`/`pj_functions` from body (default `[]`, normalize via `_normalized_list_for_cache`); add to `_query_id_input` (682-689) and `job_params` (718-728); forward to `execute_primary_query` (694-703); silently ignore `pj_bop`. | backend-engineer |
| IP-5 | SQL template | VERIFY ONLY: `{{ BASE_WHERE }}` at `sql/reject_history/performance_daily_lot.sql:70` is the single injection slot; `c.PJ_TYPE`/`c.PRODUCTLINENAME`/`c.PJ_FUNCTION` are LEFT JOIN columns from `DWH.DW_MES_CONTAINER c`. No file edit. | backend-engineer |
| IP-6 | API contract | Add three optional request params to the primary query endpoint in `contracts/api/api-contract.md` (+ `api-inventory.md` if it lists request fields); minor schema entry in `contracts/CHANGELOG.md`; regenerate BOTH `contracts/openapi.json` AND `contracts/api/openapi.json`. | backend-engineer |
| IP-7 | data-shape contract | Document request-side filter param shape and `(NA)` sentinel handling for nullable LEFT JOIN columns in `contracts/data/data-shape-contract.md`. | backend-engineer |
| IP-8 | business-rules contract | Document prefilter semantics: empty selection = no restriction; `NVL/TRIM` sentinel `(NA)`; PJ_BOP explicitly out of scope. | backend-engineer |
| IP-9 | legacy job: `reject_query_job_service.py` (CER-2) | `execute_reject_query_job` (124-191) reads the three fields from `job_params` and forwards them to `execute_primary_query`. | backend-engineer |
| IP-10 | unified job: `workers/reject_history_worker.py` (CER-3) | The `reject_unified` job applies the three `job_params` fields identically to the legacy path (RHPF-05). | backend-engineer |
| IP-11 | frontend core: `core/reject-history-filters.ts` | Add `pjTypes` / `primaryPackages` / `pjFunctions` to `RejectFilterInput` + `RejectFilterSnapshot` + `toRejectFilterSnapshot` (normalize via existing `normalizeArray`). Keep the existing supplementary `packages` field separate. | frontend-engineer |
| IP-12 | frontend: `reject-history/components/FilterPanel.vue` | Add three `MultiSelect` controls in the primary query section (same layer as date range). Options from `GET /api/production-history/filter-options?selected=<json>` (4-tuple pj_types/packages/bops/pj_functions — ignore bops). Debounce-on-close (production-history `useFirstTierFilters.ts` pattern). Empty selection sends `[]`. No PJ_BOP control. | frontend-engineer |
| IP-13 | frontend: `reject-history/App.vue` | Add reactive state for the three selections; wire to FilterPanel; include in the primary query POST payload (send `[]` when empty, never `undefined`). | frontend-engineer |
| IP-14 | tests | Add/extend all tests named in `test-plan.md` (service, routes, async-routes, contract, validation, playwright). CER-4/CER-5 cover dataset-cache and legacy-job test files. | backend-engineer + frontend-engineer |

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| change-classification.md | Inferred Acceptance Criteria AC-1..AC-7; Parity Risk | criteria + RHPF-05 |
| change-request.md | Constraints (BASE_WHERE not WHERE_CLAUSE; NVL/TRIM) | injection rule |
| test-plan.md | Test Names; AC->Test Mapping; Notes | tests to write/run |
| test-plan.md | Test Update Contract (`_VALID_QUERY_BODY_SHORT/LONG`) | baseline body update |
| ci-gates.md | Required Gates table; Merge Eligibility | verification commands |
| contracts/api/api-contract.md | §Schema Authoring Rules | both openapi exports regen |
| contracts/business/business-rules.md | prefilter semantics section (new) | `(NA)` + empty-selection rule |
| CLAUDE.md promoted learnings | regen BOTH openapi.json copies; `monkeypatch.setattr` for module constants; per-kwarg `call_args.kwargs` | impl + test discipline |

## File-Level Plan

| path or glob | action | notes |
|---|---|---|
| src/mes_dashboard/services/reject_history_service.py | edit | New `_build_base_where(...)` near `_DEFAULT_BASE_WHERE` (275-278) / `_prepare_sql` (280-298). Do not alter `_build_where_clause` semantics. |
| src/mes_dashboard/services/reject_dataset_cache.py | edit (CER-1) | `execute_primary_query` (804-1233), `_execute_and_spool` (481-796), `_make_query_id` (154-157): thread + key the three lists; merge base_where binds. |
| src/mes_dashboard/routes/reject_history_routes.py | edit | `api_reject_history_query` (641-793): parse body, cache-key input, job_params, forward. |
| src/mes_dashboard/services/reject_query_job_service.py | edit (CER-2) | `execute_reject_query_job` (124-191): forward fields. |
| src/mes_dashboard/workers/reject_history_worker.py | edit (CER-3) | unified job: apply fields. |
| src/mes_dashboard/sql/reject_history/performance_daily_lot.sql | verify only | `{{ BASE_WHERE }}` line 70; no edit. |
| contracts/api/api-contract.md, contracts/api/api-inventory.md | edit | three optional request params. |
| contracts/openapi.json, contracts/api/openapi.json | regenerate | both exports must carry new params. |
| contracts/CHANGELOG.md | edit | minor schema version entry. |
| contracts/data/data-shape-contract.md | edit | request param shape + `(NA)` sentinel. |
| contracts/business/business-rules.md | edit | prefilter semantics; PJ_BOP excluded. |
| frontend/src/core/reject-history-filters.ts | edit | new primary-prefilter fields; keep supplementary `packages` separate. |
| frontend/src/reject-history/components/FilterPanel.vue | edit | three MultiSelects + cross-filter options + debounce-on-close. |
| frontend/src/reject-history/App.vue | edit | reactive state + payload wiring. |
| tests/test_reject_history_service.py | edit | service tests per test-plan. |
| tests/test_reject_history_routes.py | edit | route forwarding tests per test-plan. |
| tests/test_reject_history_async_routes.py | edit | async forwarding + spool-key tests; update `_VALID_QUERY_BODY_SHORT/LONG`. |
| tests/test_reject_dataset_cache.py | edit (CER-4) | `_make_query_id` / BASE_WHERE / spool-key assertions. |
| tests/test_reject_query_job_service.py | edit (CER-5) | legacy job param forwarding. |
| tests/contract/test_api_contract.py | edit | both-export param presence + sample regen. |
| frontend/tests/validation/useRejectHistory.validation.test.js | edit | payload-inclusion + empty-array + pj_bop-absent. |
| frontend/tests/playwright/reject-history-filter.spec.ts | edit | render + payload + `(NA)` + PJ_BOP-absent. |

## Contract Updates

- API: `contracts/api/api-contract.md` + `api-inventory.md` — three optional request
  params on `POST /api/reject-history/query`; minor entry in `contracts/CHANGELOG.md`;
  regenerate BOTH `contracts/openapi.json` AND `contracts/api/openapi.json`.
- CSS/UI: none — additive MultiSelect reuse; no new `@layer`/unscoped rules.
- Env: none.
- Data shape: `contracts/data/data-shape-contract.md` — request param shape + `(NA)`
  sentinel for nullable LEFT JOIN columns.
- Business logic: `contracts/business/business-rules.md` — empty=no-restriction;
  `NVL/TRIM` `(NA)` semantics; PJ_BOP out of scope.
- CI/CD: none.

## Constraint Checklist (implementation MUST verify)

- [ ] Prefilters render in `{{ BASE_WHERE }}` (reject_raw CTE, before GROUP BY), NOT
      `{{ WHERE_CLAUSE }}` (AC-2). Assert via `test_build_where_clause_prefilters_absent_from_where_clause_fragment`.
- [ ] Form is `NVL(TRIM(c.PJ_TYPE|PRODUCTLINENAME|PJ_FUNCTION), '(NA)') IN (...)` — never raw
      column reference (AC-3). NULL-container rows not dropped; selecting `(NA)` returns them.
- [ ] Empty/absent selection produces identical SQL, cache key, and spool key to current
      behavior (AC-4, RHPF-05). New bind params absent when lists empty.
- [ ] The three fields appear in `_query_id_input`/`_make_query_id` AND the spool key AND
      all `job_params` paths (sync + legacy + unified) (RHPF-05).
- [ ] `pj_bop` never accepted, forwarded, rendered, or shown in UI (AC-6).
- [ ] Bind param names for the three IN-lists do not collide with `:start_date`/`:end_date`
      or any WHERE_CLAUSE binds (QueryBuilder counter forwarding).
- [ ] Frontend primary `packages` prefilter is distinct from the existing supplementary
      `packages` field; both reach the backend in their correct layer.
- [ ] Both `contracts/openapi.json` and `contracts/api/openapi.json` carry the new params.

## Test Execution Plan

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | tests/test_reject_history_routes.py | route accepts + forwards three params |
| AC-1 | tests/contract/test_api_contract.py | both openapi exports expose params; samples regen |
| AC-2 | tests/test_reject_history_service.py | prefilters in BASE_WHERE, absent from WHERE_CLAUSE |
| AC-3 | tests/test_reject_history_service.py | NVL/TRIM `(NA)` form; NULL rows matched |
| AC-4 | tests/test_reject_history_service.py | empty/absent = no restriction |
| AC-5 | frontend/tests/validation/useRejectHistory.validation.test.js | payload includes three fields |
| AC-5 | frontend/tests/playwright/reject-history-filter.spec.ts | three MultiSelects render |
| AC-6 | tests/test_reject_history_service.py | `pj_bop` absent from all SQL paths |
| AC-7 | tests/test_reject_history_async_routes.py | spool/cache key includes all three; sync/async parity |

Run order (floor = collect, targeted, changed-area; this change adds contract):
1. `cdd-kit test run --phase collect`
2. `cdd-kit test run --phase targeted`
3. `cdd-kit test run --phase changed-area`
4. `cdd-kit test run --phase contract` (openapi export parity — both copies; sample regen)

Gate commands per ci-gates.md: `cdd-kit validate`, `cdd-kit validate --contracts`,
`ruff check .`, the `unit-mock-integration` pytest selector, `cd frontend && npm run test`,
`npm run css:check`, and the two Playwright suites. Implementation agents generate
`test-evidence.yml` via `cdd-kit test run`; do not hand-author evidence.

Discipline reminders (do not re-derive — see test-plan.md Notes + CLAUDE.md):
- Per-kwarg `call_args.kwargs[key]`, never `assert_called_once_with()`.
- Async tests mock `is_async_available()=True` + enqueue fn (CI has no Redis).
- Module-level constants via `monkeypatch.setattr()`, not `setenv`.
- After full pytest runs, `git checkout tests/contract/samples/` for unrelated churn;
  re-stage only the samples this change altered.

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan. CER-gated files (CER-1..CER-5) must NOT
  be edited until their CER is approved; if approval changes the integration shape, update
  this plan before proceeding.

## Known Risks

- RHPF-05 parity (CRITICAL): four code paths must apply prefilters identically — sync
  (`execute_primary_query`), cache/spool key (`_make_query_id`/`_execute_and_spool`),
  legacy job (`execute_reject_query_job`), unified job (`reject_history_worker`). A miss in
  any one yields stale cache hits or async/sync result divergence. Gated behind CER-1/2/3.
- Allowed-paths gap: the real BASE_WHERE injection + spool-key sites are outside current
  context. Plan is `blocked` until CER-1..CER-5 are approved.
- Bind-param collision: `_build_base_where` and `_build_where_clause` both use QueryBuilder;
  ensure non-overlapping bind names (counter forwarding) — known repo pitfall.
- Frontend `packages` ambiguity: primary-layer vs existing supplementary field; conflation
  would silently route a prefilter to the wrong SQL layer.
- code-map currency: line ranges cited from `.cdd/code-map.yml`; if stale, re-run
  `cdd-kit code-map` before editing.
