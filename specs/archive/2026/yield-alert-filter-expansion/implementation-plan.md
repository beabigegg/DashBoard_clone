---
change-id: yield-alert-filter-expansion
schema-version: 0.1.0
last-changed: 2026-07-01
---

# Implementation Plan: yield-alert-filter-expansion

## Objective

Deliver two contract-driven behavior changes to the yield-alert-center feature (contracts already written; this plan is the execution packet):

1. **process_type enum expansion** — accept 6 `process_type` values `{GA%, GC%, GD%, F%, W%, D%}` (was `{GA%, GC%}`) in `POST /api/yield-alert/query` validation, so ~1.65% of previously-invisible transactions (WIP_ENTITY_NAME prefixes GD/F2/FA/FB/D2/W2) become queryable. Each value must produce a distinct `query_id`/spool via the existing hash + LIKE mechanism (no structural SQL change).
2. **workcenter_groups source swap** — for `GET /api/yield-alert/view` (`data.filter_options.workcenter_groups`) and `GET /api/yield-alert/cross-filter-options` (`data.workcenter_groups`) ONLY, compute `workcenter_groups` as `SELECT DISTINCT DEPARTMENT_NAME` against the `query_id` spool (raw, trimmed values, sorted alphabetically), replacing the global `filter_cache.get_workcenter_groups()` / grouping layer for this page. `GET /api/yield-alert/filter-options` stays on the shared cache path, unchanged. Server + DuckDB-WASM client paths must stay in parity.

Frontend: process-type selector gains 4 options with labels 重工(GD%)/委外(F%)/WIP(W%)/其他(D%); wire the two `/view` + `/cross-filter-options` responses to surface the new spool-derived `workcenter_groups`.

## Execution Scope

### In Scope
- Backend request-validation frozenset widening for `process_type` (routes).
- Confirm (no structural edit) the `_PRIMARY_DETAIL_SQL` LIKE bind + `_make_query_id` hash already generalize to the 4 new values.
- Net-new `workcenter_groups` option dimension (reading raw `DEPARTMENT_NAME`) added to `_query_filter_options()` and `compute_cross_filter_options()` in `yield_alert_sql_runtime.py`.
- DuckDB-WASM client parity: same dimension added to `useYieldAlertDuckDB.ts` `queryFilterOptions()` (§3.16.6).
- Frontend `PROCESS_TYPE_OPTIONS` +4 entries; App.vue wired to read `workcenter_groups` from `/view.filter_options` and `/cross-filter-options`.
- Test updates/additions per test-plan.md §Test Update Contract and §Acceptance Criteria → Test Mapping.

### Out of Scope
(See change-request.md §Non-goals for the authoritative list.)
- Redesign of `yield_pct` calculation.
- GA% sub-split by `WIP_CLASS_CODE` (business-rules.md YA-02a — single option stays).
- Any edit to `filter_cache.get_workcenter_groups()`, `config/workcenter_groups.py`, `get_yield_workcenter_group_options()`, `_YIELD_WORKCENTER_GROUP_ORDER`, `_DEPT_SEQ_MAP`, or the `/api/yield-alert/filter-options` endpoint (YA-11 / AC-8 — these stay untouched; only re-point the two named endpoints).
- Any spool column add/remove/rename or `_CACHE_SCHEMA_VERSION` bump (DEPARTMENT_NAME already written; see Known Risks).
- resilience / fuzz / stress / soak test families.
- The `其他(D%)` label wording decision (ui-ux-reviewer + i18n concern; not an implementation-planner or test target).

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | backend / routes | In `api_yield_alert_query` widen `_VALID_PROCESS_TYPES` (currently function-local frozenset at `yield_alert_routes.py:158`) from `{"GA%","GC%"}` to `{"GA%","GC%","GD%","F%","W%","D%"}`. Update the error message list. Default-to-`GA%` and the `_make_query_id` hash inputs (lines 160-185) stay as-is. | backend-engineer |
| IP-2 | backend / dataset cache | Confirm-only: `_PRIMARY_DETAIL_SQL` (`yield_alert_dataset_cache.py:109`, `WHERE ... WIP_ENTITY_NAME LIKE :process_type` at :127) and `_make_query_id`/`execute_primary_query` hash inputs (:443-450) already accept any process_type value with no structural change. Do NOT alter the SQL, GROUP BY, or `_CACHE_SCHEMA_VERSION` (=5, :60). Add unit coverage proving distinct query_ids + mutually-exclusive LIKE patterns (esp. `F%` not matching GA/GC/GD/D/W). | backend-engineer |
| IP-3 | backend / sql runtime — NET-NEW dimension (READ) | In `_query_filter_options()` (`yield_alert_sql_runtime.py:731`) add a NET-NEW dimension emitting response key `workcenter_groups`, computed `SELECT DISTINCT CAST("DEPARTMENT_NAME" AS VARCHAR)` from `yield_alert_src`, same exclude-set/sort convention as lines/packages/types/functions. MUST read raw column `DEPARTMENT_NAME` — NOT `DEPARTMENT_GROUP`. See Known Risks pitfall #1. | backend-engineer |
| IP-4 | backend / sql runtime — NET-NEW dimension (CROSS-FILTER) | In `compute_cross_filter_options()` (`yield_alert_sql_runtime.py:773`) add a NET-NEW `dim_specs` tuple `("DEPARTMENT_NAME", "workcenter_groups", ["departments","lines","packages","types","functions"])` and add `"workcenter_groups"` (or `"departments"`) to every existing spec's `other_filter_keys_to_apply` list so the new dimension participates in cross-filter narrowing both directions. This is ADDITIVE — do not repurpose the existing `departments` filter key. See Known Risks pitfall #2. | backend-engineer |
| IP-5 | backend / dataset cache | Confirm-only: `apply_view` (`yield_alert_dataset_cache.py:891`) returns `filter_options` straight from `try_compute_view_from_spool` → `_query_filter_options(conn)` (`yield_alert_sql_runtime.py:944`). Once IP-3 lands, `/view.filter_options.workcenter_groups` is populated automatically. No edit to `apply_view` / `try_compute_view_from_spool` beyond confirming the pass-through. | backend-engineer |
| IP-6 | frontend / WASM client parity | In `useYieldAlertDuckDB.ts` `queryFilterOptions()` (:598-621) add the same raw-`DEPARTMENT_NAME` DISTINCT dimension emitting `workcenter_groups`, mirroring IP-3 (§3.16.6 parity). Note the WASM `buildDimensionWhere` (:183) also maps `departments`→`DEPARTMENT_GROUP` for filter-apply — leave that untouched; only the option-READ side gains DEPARTMENT_NAME. | frontend-engineer |
| IP-7 | frontend / selector | In `App.vue` extend `PROCESS_TYPE_OPTIONS` (:90-93) with 4 entries: `{value:'GD%', label:'重工 (GD%)'}`, `{value:'F%', label:'委外 (F%)'}`, `{value:'W%', label:'WIP (W%)'}`, `{value:'D%', label:'其他 (D%)'}` (final `其他(D%)` wording pending ui-ux-reviewer). The `watch(selectedProcessType…)` clear/force-requery (`:805-824`) already generalizes to any value — DO NOT special-case; verified value-change-keyed, not GA/GC-gated. | frontend-engineer |
| IP-8 | frontend / consume new workcenter_groups | In `App.vue` wire `workcenter_groups` from `/view.filter_options` (`applyFullView`, :509-513) and from `/cross-filter-options` (`fetchCrossFilterOptions`, :840-844) into `workcenterGroupOptions.value`. Today those two handlers read only lines/packages/types/functions; `workcenterGroupOptions` is seeded solely from `/filter-options` (:322-326). Without this wiring the spool-derived groups never reach the dropdown. Keep `/filter-options` seed (:316-331) as the initial-load fallback, unchanged. | frontend-engineer |
| IP-9 | contracts | Already applied — see Contract Updates. Regenerate BOTH `contracts/openapi.json` AND `contracts/api/openapi.json` if any further contract edit is made; otherwise confirm-only. | contract-reviewer |
| IP-10 | tests | Implement/extend per test-plan.md §Test Update Contract + §AC→Test Mapping. See Test Execution Plan. | test-strategist (mapping) / backend-engineer + frontend-engineer (authoring) |

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| change-request.md | §Non-goals, §Resolved Decisions | scope boundary; workcenter_groups → raw DEPARTMENT_NAME decision |
| change-classification.md | §Inferred Acceptance Criteria (AC-1..AC-8) | required-changes ↔ AC mapping |
| test-plan.md | §Acceptance Criteria → Test Mapping, §Test Update Contract, §Test Execution Ladder | tests to run/write, existing tests to extend, phase floor |
| ci-gates.md | §Required Gates table, §Required Check Policy, §Rollback Policy | verification commands, no-rm/no-schema-bump confirmation |
| contracts/api/api-contract.md | endpoint row (:153), Compatibility Notes (:470) | accepted process_type set; workcenter_groups value-source semantics; JSON key unchanged |
| contracts/data/data-shape-contract.md | §3.16.4, §3.16.5, §3.16.6 | process_type scope; workcenter_groups payload swap (DEPARTMENT_NAME not DEPARTMENT_GROUP); WASM parity requirement |
| contracts/business/business-rules.md | YA-01, YA-02, YA-02a, YA-10, YA-11, YA-12 | LIKE mutual-exclusivity, enum, non-split, spool-source rule, shared-cache-unaffected, empty-spool behavior |
| agent-log/contract-reviewer.yml | concerns #1/#2 | raw vs normalized column; net-new (not re-point) dimension |
| agent-log/test-strategist.yml | col_map collision note (:20-24) | `_build_dimension_filter_sql` DEPARTMENT_GROUP at :156; fixture missing DEPARTMENT_NAME |

(No design.md — change-classification.md sets Architecture Review = no; none required.)

## File-Level Plan

| path or glob | action | notes |
|---|---|---|
| src/mes_dashboard/routes/yield_alert_routes.py | edit | IP-1: widen `_VALID_PROCESS_TYPES` (:158) + error msg. No other edit — `/view` (:325), `/cross-filter-options` (:631), `/filter-options` (:615) route bodies unchanged (source swap lives in sql_runtime). |
| src/mes_dashboard/services/yield_alert_dataset_cache.py | confirm (no edit) | IP-2/IP-5: LIKE bind (:127), hash (:443-450), `_CACHE_SCHEMA_VERSION` (:60), `_DETAIL_COLUMNS` incl. DEPARTMENT_NAME (:72) + DEPARTMENT_GROUP (:73), `apply_view` pass-through (:969). No structural change. |
| src/mes_dashboard/services/yield_alert_sql_runtime.py | edit | IP-3 `_query_filter_options()` (:731); IP-4 `compute_cross_filter_options()` dim_specs (:794-799) + other_keys lists. Do NOT touch `_build_dimension_filter_sql` col_map (:155-158, `departments`→`DEPARTMENT_GROUP`) — filter-APPLY stays as-is. |
| src/mes_dashboard/services/filter_cache.py | read-only | Confirm untouched (YA-11). |
| src/mes_dashboard/config/workcenter_groups.py | read-only | Confirm untouched. |
| frontend/src/yield-alert-center/useYieldAlertDuckDB.ts | edit | IP-6: `queryFilterOptions()` (:598) new DEPARTMENT_NAME dimension. `buildDimensionWhere` (:181) untouched. |
| frontend/src/yield-alert-center/App.vue | edit | IP-7 `PROCESS_TYPE_OPTIONS` (:90); IP-8 read `workcenter_groups` in `applyFullView` (:509) + `fetchCrossFilterOptions` (:840). Watcher (:805) confirm-only. i18n: sync any new user-visible label across all language files. |
| tests/test_yield_alert_routes.py | edit | AC-2/AC-5/AC-7/AC-8 rows + Test Update Contract (extend `test_query_requires_valid_process_type`, `test_view_supports_workcenter_group_filters`, `test_cross_filter_options_forwards_query_id_and_filters`, `test_filter_options_returns_workcenter_groups`; add zero-row + spool-source cases). |
| tests/test_yield_alert_dataset_cache.py | edit | AC-3 rows: rename `test_primary_query_id_differs_for_ga_and_gc`→`…_for_each_process_type` (6-way), add LIKE mutual-exclusivity + `F%` pattern tests. |
| tests/test_yield_alert_sql_runtime.py | edit | AC-5/AC-6 rows: add `DEPARTMENT_NAME` column to `TestCrossFilterOptions` fixture (:104-126), add `workcenter_groups` result assertions, add `test_departments_use_raw_department_name_not_department_group`, narrowing both directions, process_type/query_id variance. |
| frontend/tests/validation/useYieldAlert.validation.test.js | edit | AC-1/AC-2: expand `['GA%','GC%']` closed-list (process_type block ~:225-256) to the 6-value enum. |
| frontend/tests/yield-alert/App.cross-filter.test.js | edit | AC-4: extend watcher/force-requery coverage over 4 new values. |
| frontend/tests/yield-alert/useYieldAlertDuckDB.departments.test.js | add | AC-6 unit: WASM `queryFilterOptions` includes `workcenter_groups` from DEPARTMENT_NAME. |
| frontend/tests/playwright/yield-alert-center.spec.ts | edit | AC-1/AC-4: 6-option render + parametrize per-option query round trip (see ci-gates.md Notes: not CI-wired; run locally). |
| tests/e2e/test_yield_alert_e2e.py | edit | AC-4/AC-7: add cases for 4 new values incl. zero-row (workflow_dispatch only per ci-gates.md). |
| tests/contract/samples/, tests/contract/response-samples.json, tests/contract/test_capture_samples.py | regen/restage | AC-2 contract: re-capture yield-alert samples per CLAUDE.md churn procedure (`git checkout tests/contract/samples/` then re-stage only yield-alert samples). |
| contracts/openapi.json, contracts/api/openapi.json | regen (if further contract edit) | keep both mirrors in sync (openapi-sync gate). |

## Contract Updates

All contract edits are ALREADY APPLIED (per agent-log/contract-reviewer.yml). Reference by section; do not restate or re-edit unless a defect is found.
- **API:** `contracts/api/api-contract.md` (schema-version 1.35.0) — endpoint row for `/api/yield-alert/cross-filter-options` (:153), Compatibility Notes entry (:470). openapi.json + api/openapi.json regenerated and `cdd-kit validate --contracts` green.
- **CSS/UI:** none authored. Selector stays scoped under yield-alert theme (css-contract Rule 6). No design-token change.
- **Env:** none — no flag/env/secret added (not flag-gated).
- **Data shape:** `contracts/data/data-shape-contract.md` (1.32.0) §3.16.4 (process_type scope), §3.16.5 (workcenter_groups payload swap; column source = raw DEPARTMENT_NAME, NOT DEPARTMENT_GROUP; JSON key unchanged; query-dependent; empty-spool → empty array), §3.16.6 (DuckDB-WASM parity).
- **Business logic:** `contracts/business/business-rules.md` (1.38.0) YA-01 (6-value enum, default GA%, 400 on invalid), YA-02 (prefix→WIP_CLASS_CODE mapping + LIKE disjointness), YA-02a (no GA split), YA-10 (spool-derived DEPARTMENT_NAME, not DEPARTMENT_GROUP), YA-11 (shared cache/filter-options unaffected), YA-12 (empty-spool → empty array, not 500).
- **CI/CD:** none — rides existing gate set (ci-gates.md §New Workflow Changes: None).

## Test Execution Plan

Required phase floor (test-plan.md §Test Execution Ladder): `collect`, `targeted`, `changed-area`; plus `contract` (samples affected) and `full` at CI. Implementation agents generate evidence with `cdd-kit test run`; the gate validates `test-evidence.yml`. `cdd-kit test select` reads the `test file / command` targets below.

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | frontend/tests/validation/useYieldAlert.validation.test.js | selector renders exactly 6 process_type options |
| AC-2 | tests/test_yield_alert_routes.py | each of {GA%,GC%,GD%,F%,W%,D%} accepted; near-miss (e.g. `G%`) → 400 VALIDATION_ERROR |
| AC-2 | tests/contract/test_capture_samples.py | recaptured yield-alert samples reflect expanded enum |
| AC-3 | tests/test_yield_alert_dataset_cache.py | distinct query_id per process_type; LIKE patterns mutually exclusive (`F%` ⊄ GA/GC/GD/D/W) |
| AC-4 | frontend/tests/yield-alert/App.cross-filter.test.js | switching to any new process_type clears query_id + forces re-query |
| AC-5 | tests/test_yield_alert_sql_runtime.py | `_query_filter_options()`/`compute_cross_filter_options()` return `workcenter_groups` from `SELECT DISTINCT DEPARTMENT_NAME`; raw DEPARTMENT_NAME not DEPARTMENT_GROUP |
| AC-5 | tests/test_yield_alert_routes.py | `/view` + `/cross-filter-options` workcenter_groups spool-sourced; `filter_cache.get_workcenter_groups` NOT called on these two |
| AC-6 | tests/test_yield_alert_sql_runtime.py | cross-filter narrowing both directions for the new dimension; workcenter_groups varies with process_type/query_id |
| AC-6 | frontend/tests/yield-alert/useYieldAlertDuckDB.departments.test.js | WASM `queryFilterOptions` includes `workcenter_groups` (§3.16.6 parity) |
| AC-7 | tests/test_yield_alert_routes.py | new process_type with zero rows → valid empty result, not 500 (YA-12) |
| AC-7 | tests/e2e/test_yield_alert_e2e.py | new process_type values return valid rows; zero-row case empty-not-error (workflow_dispatch) |
| AC-8 | tests/test_yield_alert_routes.py | `/filter-options` still calls `get_yield_workcenter_group_options` → `filter_cache.get_workcenter_groups` unchanged |

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.
- **Pitfall #1 (raw vs normalized column) — MUST NOT get wrong:** the new `workcenter_groups` option dimension reads raw `DEPARTMENT_NAME` (trimmed-only spool column, `_DETAIL_COLUMNS` :72). It MUST NOT read `DEPARTMENT_GROUP` (the normalized column `_normalize_yield_department_group()` produces, :73/:174). `_build_dimension_filter_sql` col_map (`yield_alert_sql_runtime.py:155-158`) intentionally maps the `departments` FILTER-APPLY key to `DEPARTMENT_GROUP` — that is a separate concern and stays. Filter-apply on `departments` = DEPARTMENT_GROUP; option-read for `workcenter_groups` = DEPARTMENT_NAME. Both coexist. (data-shape §3.16.5, YA-10, contract-reviewer concern #2, test-strategist col_map note.)
- **Pitfall #2 (net-new dimension, NOT a re-point) — MUST NOT get wrong:** `workcenter_groups` does not exist today as a spec in `_query_filter_options()` / `compute_cross_filter_options()` (`dim_specs` at :794-799 covers only lines/packages/types/functions; `_query_filter_options` at :734-739 same). `departments` already appears in `other_filter_keys_to_apply` lists but has NO producing dim_spec. The task is to ADD a new dimension (col=DEPARTMENT_NAME, key=`workcenter_groups`), not to rename/repurpose an existing one. Add it to every existing spec's `other_keys` list so cross-filter narrows in both directions. (contract-reviewer concern #1, test-strategist :19-24.)
- **Response JSON key is `workcenter_groups`, not `departments`:** the API/data-shape contracts (§3.16.5, Compatibility Notes) require the option key emitted in `/view.filter_options` and `/cross-filter-options` to be `workcenter_groups`. The `departments` name is the request-filter-parameter key (`_common_filters()` at routes :108, `_build_dimension_filter_sql` key), distinct from the response option key. Do not emit `departments` as a response key.
- **`/api/yield-alert/filter-options` stays unchanged** (YA-11/AC-8): it uses `get_yield_workcenter_group_options()` (yield_alert_service.py:210) → `filter_cache.get_workcenter_groups()` (:213) + grouping/ordering. Do not touch this path; add a regression assertion instead.
- **No spool schema change:** DEPARTMENT_NAME is already written to every spool (`_DETAIL_COLUMNS` :72). Do NOT add/remove/rename columns, do NOT bump `_CACHE_SCHEMA_VERSION` (=5), do NOT add an `rm -f …/yield_alert_dataset/*.parquet` step. This is a read-side query change only (ci-gates.md §Rollback Policy; see Known Risks).
- i18n: new user-visible selector labels must be synced across ALL language files (per user global i18n rule); do not update only one language.

## Known Risks
- **Contract-wording tension on rollback/rm:** data-shape §3.16.4 (:1094) carries a generic "Breaking-change surface: … `rm -f tmp/query_spool/yield_alert_dataset/*.parquet` required on both deploy and rollback" note, and YA-09 requires a `_SCHEMA_VERSION` bump for column changes. THIS change makes no column change, so neither applies — ci-gates.md §Rollback Policy explicitly states no rm and no schema bump are needed (plain code revert). Backend-engineer must NOT over-apply the §3.16.4/YA-09 breaking-change procedure to this change. If a spool column change ever becomes necessary, that would re-open this and require a schema bump + rm — but it is out of scope here.
- **Cross-filter narrowing coupling:** adding `workcenter_groups`/`departments` to every existing spec's `other_filter_keys_to_apply` means the existing `departments` filter (applied via DEPARTMENT_GROUP) narrows the new DEPARTMENT_NAME option list. Since DEPARTMENT_NAME is finer-grained than DEPARTMENT_GROUP, a `departments`(=group) selection narrows workcenter_groups(=raw names) to the raw names within that group — intended per YA-10 (same mechanism as other dims). Test both directions (test-plan.md AC-6) to lock this.
- **WASM/server drift:** `useYieldAlertDuckDB.ts` `queryFilterOptions` and server `_query_filter_options` are hand-mirrored (no shared source). If only one path gains the DEPARTMENT_NAME dimension, large queries that cross the DuckDB-WASM threshold mid-session silently lose workcenter_groups cross-filtering (§3.16.6). AC-6 WASM parity test guards this.
- **Playwright E2E not CI-wired:** `yield-alert-center.spec.ts` is not invoked by any workflow (ci-gates.md §Merge Eligibility / Notes). Extended AC-1/AC-4 Playwright assertions pass locally but do not run in CI — verify locally (`cd frontend && npx playwright test tests/playwright/yield-alert-center.spec.ts`) before approval. Do not fold a CI-wiring fix into this change's diff.
- **Contract sample churn:** running full pytest regenerates ~160 contract samples with live values; `git checkout tests/contract/samples/` then re-stage only yield-alert samples before commit (CLAUDE.md Promoted Learnings).
- **Code-map freshness:** `.cdd/code-map.yml` regenerated 2026-07-01 (cdd-kit 3.6.0), matches sources scoped here; line numbers above are from that map + direct reads.
