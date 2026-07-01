---
change-id: eap-alarm-coarse-filter
schema-version: 0.1.0
last-changed: 2026-06-30
---

# Implementation Plan: eap-alarm-coarse-filter

## Objective
Extend the EAP-alarm coarse spool filter from `(date + machines)` to
`(date + machines? + lot_ids? + product_dims?)` with at-least-one-of-three
required, push `lot_ids` (LOT_ID IN) and `product_dims` (per-dim EXISTS
semi-join on `DWH.DW_MES_CONTAINER`) into the Oracle worker query, fold all
5 coarse dims into the spool key, bump `_SCHEMA_VERSION` 2→3, add
`GET /api/eap-alarm/product-filter-options` (reusing `container_filter_cache`),
and surface LOT_ID + TYPE/PACKAGE/BOP controls in the FilterBar. Behavior must
satisfy AC-1..AC-7 (change-classification.md) and the EA-01/EA-08/EA-09/EA-10
business rules without reversing any ADR-0008 invariant.

## Execution Scope

### In Scope
- Backend: `eap_alarm_cache.py`, `eap_alarm_service.py`, `eap_alarm_worker.py`,
  `eap_alarm_routes.py` (read-only consumer of `container_filter_cache`).
- Frontend: `frontend/src/eap-alarm/` FilterBar + `useEapAlarmFilter.js` + the
  spool-POST body assembly and validation in `App.vue`.
- Contract upkeep already drafted (API/data-shape/business-rules) — verify and
  regen openapi (both exports). See Contract Updates.
- Tests per test-plan.md (unit, data-boundary, resilience, integration, fe-unit, e2e).

### Out of Scope
- Reversing ADR-0008 (fine filters / views stay DuckDB-only over parquet).
- Switching EXISTS to JOIN+DISTINCT (design.md D-3 forbids it).
- v2 parquet migration/backfill — schema_version bump self-invalidates (D-5).
- New env var / feature flag (`_SCHEMA_VERSION` is in-code).
- CSS rule changes — additive shared components under existing `.theme-eap-alarm`;
  confirm with `npm run css:check` only.
- Amending `docs/adr/0008-...md` — flagged for owner (Known Risks), not this PR's code.
- Any opportunistic refactor of `_PAIR_SQL`, fine-filter, or unified-job aggregation.

## Required Changes
| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | spool key | `eap_alarm_cache.make_eap_alarm_spool_key()`: bump `_SCHEMA_VERSION` 2→3; widen signature to accept `lot_ids, pj_types, product_lines, pj_bops`; canonical repr = sorted/stripped per-dim with fixed separator, empty list → empty string (D-1, EA-01) | backend-engineer |
| IP-2 | validation | `eap_alarm_service.validate_eap_alarm_params()`: at-least-one-of-three (EA-08); machines no longer unconditionally required; eqp_types enum check only when supplied; strip/dedup lot_ids and enforce max 200 → ValueError on overflow (EA-09, D-4) | backend-engineer |
| IP-3 | Oracle query | `eap_alarm_worker.py`: add lot_ids `LOT_ID IN (...)` binds and a `_build_product_dims_exists()` emitting one `EXISTS` clause per supplied product dim (NVL/TRIM, `c.CONTAINERNAME = e.LOT_ID`), AND-combined under existing predicate; inject into BOTH `_EAP_EVENT_SQL_TEMPLATE` and `_DETAIL_SQL_TEMPLATE`; wire through legacy `run_eap_alarm_query_job` AND unified `EapAlarmJob.pre_query/build_chunk_sql` (EA-09, EA-10, D-3) | backend-engineer |
| IP-4 | route | `eap_alarm_routes.api_eap_alarm_spool`: parse `lot_ids, pj_types, product_lines, pj_bops` from body; pass all 5 dims to validate + spool-key + both enqueue param dicts; run validation pre-key (D-4) | backend-engineer |
| IP-5 | options endpoint | `eap_alarm_routes`: add `GET /api/eap-alarm/product-filter-options` wrapping `container_filter_cache.get_filter_options()`; MAP cache keys `packages→product_lines`, `bops→pj_bops`, keep `pj_types`; cold cache → empty arrays + `updated_at:null`, never 500 (D-2, EA-10, §3.17) | backend-engineer |
| IP-6 | openapi regen | regenerate BOTH `contracts/openapi.json` AND `contracts/api/openapi.json` after the endpoint/body/schema edits | backend-engineer |
| IP-7 | fe composable | `useEapAlarmFilter.js`: extend `coarseFilter` with `lot_ids:[], pj_types:[], product_lines:[], pj_bops:[]`; add `buildCoarseParams()` forwarding all 5 dims (omit empty); fetch product-filter-options on mount and expose product options (AC-6) | frontend-engineer |
| IP-8 | fe FilterBar | `FilterBar.vue` + spool-POST in `App.vue`: add LOT_ID textarea (newline-separated → array at submit), TYPE/PACKAGE/BOP MultiSelects sourced from product-filter-options; replace machines-required guard (App.vue ~L124-128) with at-least-one-of-three; build body via `buildCoarseParams()` (App.vue ~L151-155); sync i18n for new labels (PACKAGE↔PRODUCTLINENAME) (AC-3, AC-6) | frontend-engineer |
| IP-9 | tests | author/update tests per test-plan.md families table | backend-engineer (py), frontend-engineer (js/ts) |

### Round 2 — post-ship corrections (D-6/D-7/D-8; AC-8/AC-9/AC-10)
| id | area | required action | owner agent |
|---|---|---|---|
| IP-10 | worker SQL bug | `eap_alarm_worker._build_equipment_filter` (L201-216): the empty-list case (`machines == []`) currently falls into the `len <= 999` branch and returns `"e.EQUIPMENT_ID IN ()"` → ORA-00936, because this filter is spliced *unconditionally* as `AND {equipment_filter}` at L59/L71 (unlike lot/product which return `""` and are only appended when non-empty). Fix: add an explicit early branch that returns the always-true predicate `"1=1"` (with empty params `{}`) when `machines` is empty, so the unconditional splice stays valid SQL and the row set is left unrestricted by equipment. Do NOT make the splice conditional (D-6 rejected that). Add a one-line comment referencing D-6/EA-08. (owner: backend-engineer) |
| IP-11 | validation enum removal | `eap_alarm_service.py`: delete `_VALID_EQP_TYPES` (L39-41) and the enum membership block inside `validate_eap_alarm_params` (L69-71: `invalid_enum = [...]` + its `raise`). Keep the non-string/blank rejection (L65-67) and the strip (L68) — `eqp_types` is validated *exactly like `lot_ids`*: reject non-string/blank entries, keep every non-empty stripped value, no membership check (D-7). Update the docstring reference to EA-07 (L53/L56) so it no longer claims an enum check. Leave the field name `eqp_types` unchanged (design Open Risk: rename is a breaking API change for zero functional gain); add a one-line comment noting the field now holds full equipment-ID strings, not 4-char type codes. (owner: backend-engineer) |
| IP-12 | frontend family expansion | `frontend/src/eap-alarm/FilterBar.vue::handleSubmit` (L92-102): before `emit('submit')`, when `cascade.families.length > 0 && (props.filters.machines?.length ?? 0) === 0`, expand the emitted `machines` to every name in `machineOptions.value` (already the sorted full machine list of the filtered family, computed L77-81) and include it in the `update:filters` emit. Semantics (D-8): (a) family + specific machines → send those machines unchanged; (b) family + no machine → send all `machineOptions.value` names; (c) no family/no machine → leave `machines` as `[]` (unrestricted by equipment via IP-10's `1=1`). `cascade.families` is local-only and must never be sent to the backend. Reuse the already-loaded pool — no backend/worker fan-out (D-8 rejected server-side expansion). Sync i18n if any new user-visible copy is added. (owner: frontend-engineer) |
| IP-13 | round-2 tests | author/update the new and existing tests per test-plan.md AC-8/AC-9/AC-10 rows and the "Test Update Contract" table (exact file/class/test names and line pointers already listed there). Backend: `TestEquipmentFilterEmptyNoOp` (new), `test_empty_eqp_types_with_product_dims_only_builds_valid_sql` (new, resilience — required red-green signal), `TestMachinesValidation` updates + new `test_full_equipment_id_string_no_error` / `test_out_of_old_enum_value_no_longer_raises`. Frontend: `FilterBar handleSubmit family expansion` unit describe (mount via `@vue/test-utils`) + e2e family-only submission. (owner: backend-engineer for python, frontend-engineer for JS/TS/e2e) |

## Source Artifact Pointers
| source | relevant pointer | used for |
|---|---|---|
| design.md | D-1..D-5; Open Risks (CHAR padding, ADR-0008) | implementation constraints |
| test-plan.md | AC→test mapping; Test Families Required; Test Update Contract | tests to write/update + red-green signal |
| change-classification.md | AC-1..AC-7; Required Contracts | acceptance + contract scope |
| business-rules.md | EA-01, EA-08, EA-09, EA-10 (+EA-07 update) | validation/SQL/key semantics |
| data-shape-contract.md | §3.17 + Product-filter-options payload (L1129-1142) | spool key dims, options payload, key mapping |
| ci-gates.md | Required Gates table | verification gates (lint/build/unit/contract/integration/data-boundary/resilience/e2e) |
| design.md | D-6, D-7, D-8 (post-ship corrections) + Open Risks (field-name drift, family-expansion cardinality, round-2 coverage) | IP-10/11/12 implementation constraints — authoritative technical detail, do not re-derive |
| test-plan.md | AC-8/AC-9/AC-10 mapping; Round-2 rows in "Test Families Required"; updated "Test Update Contract" table (exact line pointers) | IP-13 tests to write/update + round-2 red-green signal |
| business-rules.md | EA-07 (contract prose NOT yet drafted for D-6/D-7 — contract-reviewer's next step, see Handoff Constraints) | contract-side scope boundary |

## File-Level Plan
| path or glob | action | notes |
|---|---|---|
| src/mes_dashboard/services/eap_alarm_cache.py | edit | IP-1: `_SCHEMA_VERSION=3` (L22); `make_eap_alarm_spool_key` (L34-60) signature + canonical repr |
| src/mes_dashboard/services/eap_alarm_service.py | edit | IP-2: `validate_eap_alarm_params` (L37-48) |
| src/mes_dashboard/workers/eap_alarm_worker.py | edit | IP-3: SQL templates (L48-73), `_build_equipment_filter` (L148-163) + new `_build_product_dims_exists`, `run_eap_alarm_query_job` (L166-287), `EapAlarmJob.pre_query`/`build_chunk_sql` (L315-374) |
| src/mes_dashboard/routes/eap_alarm_routes.py | edit | IP-4 in `api_eap_alarm_spool` (L121-239); IP-5 new product-filter-options route |
| src/mes_dashboard/services/container_filter_cache.py | read-only | IP-5 consumes `get_filter_options()` (L139-220); no edit |
| contracts/openapi.json, contracts/api/openapi.json | regen | IP-6 |
| frontend/src/eap-alarm/composables/useEapAlarmFilter.js | edit | IP-7 |
| frontend/src/eap-alarm/FilterBar.vue | edit | IP-8 LOT_ID textarea + product MultiSelects |
| frontend/src/eap-alarm/App.vue | edit | IP-8 validation (~L124-128) + body (~L151-155) |
| tests/test_eap_alarm_service.py | edit | new classes + update `TestSchemaVersionIsPinned`/`TestMachinesValidation` (test-plan Test Update Contract) |
| tests/integration/test_eap_alarm_data_boundary.py | edit | data-boundary cases (`pytestmark = integration`) |
| tests/integration/test_eap_alarm_resilience.py | edit | 3 new resilience cases |
| tests/integration/test_eap_alarm_rq_async.py | edit | `TestEapAlarmWorkerFnNewDims`; per-kwarg route-forwarding asserts |
| frontend/tests/unit/eap-alarm-filter.test.js | edit | `describe('buildCoarseParams')` per-kwarg |
| frontend/tests/playwright/eap-alarm-filters.spec.ts | create | e2e LOT_ID + product-dim + machines-optional + all-empty-400 |

### Round 2 — post-ship corrections (D-6/D-7/D-8) — line pointers confirmed against refreshed code-map (2026-07-01)
| path or glob | action | notes |
|---|---|---|
| src/mes_dashboard/workers/eap_alarm_worker.py | edit | IP-10: `_build_equipment_filter` (L201-216) — add empty-`machines` → `return "1=1", {}` branch. Covers BOTH callers (`run_eap_alarm_query_job` L256, `EapAlarmJob.__init__` L414) with one edit — same helper, confirmed. Splice site is `AND {equipment_filter}` at L59 (`_EAP_EVENT_SQL_TEMPLATE`) / L71 (`_DETAIL_SQL_TEMPLATE`); leave templates unchanged. |
| src/mes_dashboard/services/eap_alarm_service.py | edit | IP-11: remove `_VALID_EQP_TYPES` (L39-41) + `invalid_enum` check (L69-71); keep non-string/blank reject (L65-67) + strip (L68); update docstring EA-07 wording (L53/L56); add field-name-drift comment. No signature change. |
| frontend/src/eap-alarm/FilterBar.vue | edit | IP-12: `handleSubmit` (L92-102) — family-without-machine expansion; reuse `machineOptions` computed (L77-81) + `cascade.families` (L65-67). No template/prop change required. |
| tests/test_eap_alarm_service.py | edit | IP-13: new `TestEquipmentFilterEmptyNoOp` (pure fn, no mock); update `TestMachinesValidation` (`test_single_valid_eqp_type_no_error` L160-162, `test_multiple_valid_eqp_types_no_error` L164-166 — rescope to non-enum; `test_empty_string_in_list_raises_value_error` L180-183 keep) + add `test_full_equipment_id_string_no_error`, `test_out_of_old_enum_value_no_longer_raises`. |
| tests/integration/test_eap_alarm_resilience.py | edit | IP-13: add `test_empty_eqp_types_with_product_dims_only_builds_valid_sql` (mock `read_sql_df_slow` like `test_oracle_failure_during_spool`; assert captured SQL contains `1=1` and NOT `IN ()`) — round-2 red-green signal; `pytestmark = pytest.mark.integration`. |
| frontend/tests/unit/eap-alarm-filter.test.js | edit | IP-13: add `describe('FilterBar handleSubmit family expansion')` (mount `FilterBar.vue` via `@vue/test-utils`) — 3 cases per AC-10. |
| frontend/tests/playwright/eap-alarm-filters.spec.ts | edit (created in IP-9) | IP-13: add family-only submission e2e (mocked API) asserting backend receives full machine list. |

## Contract Updates
All contract prose is already drafted (see CHANGELOG entries in business-rules.md L458 / data-shape-contract.md L1573). Implementation must keep code in sync — do not re-author prose; verify and regen only.
- API: `contracts/api/api-contract.md` + `api-inventory.md` — new body fields (`lot_ids`, `pj_type/product_line/pj_bop`), `machines` optional, `GET /api/eap-alarm/product-filter-options`. Regen BOTH openapi exports (IP-6).
- CSS/UI: none — additive shared components under `.theme-eap-alarm`; `npm run css:check` only.
- Env: none.
- Data shape: `data-shape-contract.md` §3.17 + Product-filter-options payload (`{pj_types, product_lines, pj_bops, updated_at}`, cold-cache empty arrays). Code must honor the cache-key→payload mapping (IP-5).
- Business logic: `business-rules.md` EA-01 (5-dim key), EA-08 (at-least-one), EA-09 (lot_ids strip/dedup/max-200), EA-10 (EXISTS semi-join), EA-07 (eqp_types enum only-when-supplied).
- CI/CD: none — existing eap-alarm gates cover it.

## Test Execution Plan
Required phase floor: `collect`, `targeted`, `changed-area`; add `contract` (API/openapi edits) and `full` before pushing a behavioral/data-shape change (CLAUDE.md: `gate --strict` runs only changed-area). Generate evidence with `cdd-kit test run`; the gate validates `test-evidence.yml`. Mappings below mirror test-plan.md — defer to it as source of truth.

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 lot_ids→IN; key reflects lot_ids | tests/test_eap_alarm_service.py::TestSpoolKeyComposition | distinct lot_ids → distinct key; key contains lot_ids dim |
| AC-1 (integration) | tests/integration/test_eap_alarm_rq_async.py::TestEapAlarmWorkerFnNewDims | `LOT_ID IN` present in SQL; route forwards lot_ids per-kwarg |
| AC-2 product_dims EXISTS, no dup | tests/test_eap_alarm_service.py::TestProductDimsFilter | one EXISTS clause per supplied dim; AND-combined |
| AC-2 (data-boundary) | tests/integration/test_eap_alarm_data_boundary.py | no-match → 0 rows; no row explosion |
| AC-3 at-least-one; all-empty→400 | tests/test_eap_alarm_service.py::TestAtLeastOneFilterRequired | all-empty raises; any one axis passes |
| AC-3 (route 400) | tests/integration/test_eap_alarm_resilience.py | all-filters-empty → 400 VALIDATION_ERROR |
| AC-4 key stability + schema_version=3 | tests/test_eap_alarm_service.py::TestSchemaVersionIsPinned | asserts `== 3` (red before, green after) |
| AC-5 mixed-axis AND; lot_id normalize | tests/test_eap_alarm_service.py::TestLotIdNormalization | whitespace/dup stripped; >200 → error |
| AC-5 (CHAR-pad / intersection) | tests/integration/test_eap_alarm_data_boundary.py | CHAR-padded CONTAINERNAME matches stripped lot_id; intersection only |
| AC-6 FilterBar + buildCoarseParams | frontend/tests/unit/eap-alarm-filter.test.js (describe buildCoarseParams) | each dim forwarded per-kwarg; empty omitted; machines-absent ok |
| AC-6 (e2e) | frontend/tests/playwright/eap-alarm-filters.spec.ts | LOT_ID textarea + product MultiSelects submit; machines-optional 200 |
| AC-7 Oracle error / cache miss | tests/integration/test_eap_alarm_resilience.py | EXISTS Oracle error fails over (no 503 leak); cache miss → empty arrays not 500 |
| AC-8 empty eqp_types → `1=1` no-op | tests/test_eap_alarm_service.py::TestEquipmentFilterEmptyNoOp | `_build_equipment_filter([])` returns SQL fragment `1=1`, not `e.EQUIPMENT_ID IN ()` (pure fn, no mock) |
| AC-8 (resilience, red-green signal) | tests/integration/test_eap_alarm_resilience.py::test_empty_eqp_types_with_product_dims_only_builds_valid_sql | `run_eap_alarm_query_job(eqp_types=[], product_lines=["SOT-223"])` captured SQL contains `1=1`, no `IN ()`; fails before IP-10, passes after |
| AC-9 eqp_types validated like lot_ids (no enum) | tests/test_eap_alarm_service.py::TestMachinesValidation | any non-empty stripped string passes; blank still rejected |
| AC-9 real EQUIPMENT_ID shape passes | tests/test_eap_alarm_service.py::TestMachinesValidation::test_full_equipment_id_string_no_error | `eqp_types=["GWBK-0241"]` passes; `test_out_of_old_enum_value_no_longer_raises` proves membership check gone |
| AC-10 family-only → full machine list | frontend/tests/unit/eap-alarm-filter.test.js (describe 'FilterBar handleSubmit family expansion') | family + empty machines → emitted `machines` = all filtered `machineOptions`; family + explicit machines unchanged; no family/no machine → `machines` stays `[]` |
| AC-10 (e2e) | frontend/tests/playwright/eap-alarm-filters.spec.ts | family-only submission (mocked API) reaches backend with full machine list |

## Handoff Constraints
- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.
- Apply the lot_id/CONTAINERNAME strip consistently at BOTH key-build and Oracle bind (design.md Open Risk).
- Wire new dims through BOTH worker paths (legacy `run_eap_alarm_query_job` and unified `EapAlarmJob`); the `_EAP_ALARM_USE_UNIFIED_JOB` flag selects one at runtime — a one-path edit silently breaks the other.
- IP-10 covers BOTH worker paths with a single edit: `run_eap_alarm_query_job` (L256) and `EapAlarmJob.__init__` (L414) both call the same `_build_equipment_filter` helper (confirmed against the refreshed worker file). Do not add a second edit; do not duplicate the `1=1` branch inline at either call site.
- Contract prose scope for round 2: unlike IP-1..IP-9 (whose contract prose was "already drafted — verify only"), the EA-07 contract text in `contracts/business/business-rules.md` for D-6/D-7 is NOT yet drafted. This plan covers code + tests only. contract-reviewer must WRITE new EA-07 prose in the next step (document: eqp_types is validated like lot_ids with no closed enum; the field name is retained but now holds full equipment-ID strings not 4-char codes; empty eqp_types is a legal EA-08 axis yielding an unrestricted-by-equipment predicate). Do not author or edit that prose here. D-8 is a frontend-only client-side behavior with no contract-prose obligation.

## Known Risks
- CHAR-padding foot-gun: `DW_MES_CONTAINER.CONTAINERNAME` is space-padded; TRIM must be applied on both sides or a stripped lot_id mints a key that mismatches Oracle (design.md). Covered by data-boundary test.
- Two worker code paths must stay in lockstep (flag-gated); easy to edit one and miss the other.
- product-filter-options cache-key→payload mapping (`packages→product_lines`, `bops→pj_bops`) is non-obvious; getting it wrong yields silently mislabeled options. Pin with a contract/route test.
- Cold `container_filter_cache` renders empty MultiSelects (reads as "no products"); UI empty-state copy owned by ui-ux-reviewer, not this plan.
- ADR-0008 is still `proposed` and its text says coarse key = `sha256(sorted(eqp_types))`; it should be amended to 5 dims + EXISTS-not-JOIN rule (owner action, flagged in design.md — not this PR's code).
- (Round 2) IP-10's `1=1` no-op must NOT be turned into a conditional splice; the templates keep `AND {equipment_filter}` unchanged (design D-6 rejected the conditional-splice alternative). The round-1 unit tests exercised non-empty `eqp_types` and non-empty product_dims separately but never the `eqp_types=[]` + product-dim combination (the ORA-00936 shape) — AC-8's two rows close that exact gap; `_build_equipment_filter` tests must not stay single-argument-only.
- (Round 2) IP-11 keeps the field name `eqp_types` even though it now holds full equipment-ID strings (`GWBK-0241`), not 4-char type codes — a rename would break API body / openapi / spool-key repr / frontend / tests for no functional gain (design Open Risk). The misnomer is documented in a code comment + EA-07 prose (contract-reviewer), not fixed by rename. Do not rename the field opportunistically.
- (Round 2) IP-12 client-side family expansion can send a large `machines` list for a family with hundreds of tools; the worker's `_build_equipment_filter` OR-of-INs branch (L207-216) already handles > 999 binds, so this is bounded. Roster drift between submits yields distinct spool keys (correct, slightly less cache reuse) — noted so it is not mistaken for a bug.
