# Archive — equipment-rejects-by-lots

## Change Summary

Redesigned the query-tool equipment-rejects sub-tab from a coarse aggregate view
(one row per EQUIPMENTNAME with TOTAL_REJECT_QTY / TOTAL_DEFECT_QTY / AFFECTED_LOT_COUNT)
to a per-reject-event detail view aligned with the cross-station semantic (QT-07):
lots are resolved via LOTWIPHISTORY → CONTAINERID → LOTREJECTHISTORY, so reject events
logged under a different station than the queried equipment are intentionally included.
This change also fixed two production bugs reported mid-session: (1) lot-to-equipment
lookup never returned `lot_names` so production-records and rejects tabs showed
unrelated lots; (2) the rejects sub-tab returned full-line rejects regardless of the
user's selected workcenter groups.

## Final Behavior

- `query_type=rejects` in `/api/query-tool/equipment-period` now returns one row per
  LOTREJECTHISTORY event rather than aggregated totals.
- Columns: CONTAINERNAME, WORKCENTERNAME, WORKCENTER_GROUP, PRODUCTLINENAME,
  PJ_FUNCTION, PJ_TYPE, PRODUCTNAME, SPECNAME, LOSSREASONNAME, EQUIPMENTNAME,
  REJECTCOMMENT, REJECT_QTY, STANDBY_QTY, QTYTOPROCESS_QTY, INPROCESS_QTY,
  PROCESSED_QTY, REJECT_TOTAL_QTY, DEFECT_QTY, TXN_TIME, TXNDATE, TXN_DAY.
- Aggregate fields TOTAL_REJECT_QTY, TOTAL_DEFECT_QTY, AFFECTED_LOT_COUNT removed.
- For lot/work-order search (`useLotEquipmentQuery`): `workcenter_groups` is now
  forwarded to `get_equipment_rejects()` and applied as a `WORKCENTER_GROUP IN (...)`
  filter in SQL. Direct-equipment search (`useEquipmentQuery`) sends no groups → `1=1`.
- `resolve_lot_equipment()` now returns `lot_names` so the frontend
  `resolvedLotNames` filter activates correctly in all three sub-tabs.
- EquipmentRejectsTable.vue rewritten to match LotRejectTable pattern: sortable
  columns, breakdown-toggle for sub-qty columns, EQUIPMENTNAME labeled as
  "報廢登錄設備 (可能不同於查詢設備)" per cross-station semantic.

## Final Contracts Updated

- `contracts/api/api-contract.md` — schema-version 1.7.0; §10 compatibility note added
  (aggregate fields removed, detail rows added; monorepo hard cutover)
- `contracts/data/data-shape-contract.md` — schema-version 1.6.0 (→ 2.0.0 at first
  review, confirmed 1.6.0 in CHANGELOG); §3.7 equipment-rejects row shape added;
  §5.x CSV columns documented
- `contracts/business/business-rules.md` — schema-version 1.8.0; QT-07 rule added
- `contracts/api/api-inventory.md` — schema-version 1.1.5 (patch note)
- `contracts/CHANGELOG.md` — entries for api 1.7.0, data 1.6.0, business 1.8.0

Evidence: `agent-log/backend-engineer.yml` artifacts.contracts-touched

## Final Tests Added / Updated

Backend:
- `tests/test_query_tool_service.py::TestGetEquipmentRejects` — 3 tests:
  cross_station, no_aggregate, empty_short_circuit
- `tests/test_query_tool_routes.py::TestEquipmentPeriodRejectsDetailSchema` — 2 tests:
  detail_schema, empty_ids
- `tests/test_query_tool_no_error_dicts.py::test_QT_07_cross_station_rule_present`
- `tests/test_query_tool_heavy_join.py::TestQueryToolHeavyJoin::test_equipment_rejects_row_limit_at_scale`
- Full suite: 3979 passed, 267 skipped (excl. e2e + integration_real)

Frontend:
- `frontend/tests/query-tool/EquipmentRejectsTable.test.js` — 6 tests (new)
- Full Vitest suite: 346 passed, 1 skipped (33 files)
- `frontend/tests/playwright/query-tool.spec.js` — TODO scaffold added (Tier 3 nightly)

Evidence: `agent-log/backend-engineer.yml`, `agent-log/frontend-engineer.yml`

## Final CI/CD Gates

- Tier 0 (pre-commit / PR): Python lint, TypeScript type-check, backend unit tests,
  Vitest component tests — all green
- Tier 1 (PR): cdd-kit validate, integration + data-shape contract tests — all green
- Tier 3 (nightly): E2E playwright + pytest e2e — TODO scaffold; required before
  production promotion

Evidence: `ci-gates.md`

## Production Reality Findings

- `resolve_lot_equipment()` had silently never returned `lot_names` since the
  lot-equipment feature was first written; the frontend filter was present but
  never activated. Discovered during post-merge user testing, fixed in commit
  `a0e423d` alongside the workcenter-group filter for rejects.
- `WORKCENTER_GROUP` in the rejects SQL is spec_map-derived (`sm.WORKCENTER_GROUP`)
  with fallback to raw WORKCENTERNAME for unmapped specs. Grouping by user's selected
  workcenter groups therefore requires the spec_map to be populated for the relevant
  specs; unmapped specs fall back to WORKCENTERNAME which may not match group names.
  This is an existing data-quality gap, not introduced by this change.
- Two-builder pattern (counter-forwarding `wg_builder._param_counter`) was required
  to avoid Oracle bind-variable name collision (`p0` collision between EQUIPMENTID
  and WORKCENTER_GROUP IN conditions).

## Lessons Promoted to Standards

**Lesson A — QueryBuilder counter-forwarding** promoted to `CLAUDE.md §QueryBuilder Architecture Notes`
- Rule: When a single service function builds two independent IN-list conditions with separate `QueryBuilder` instances, forward `_param_counter` between them before and after `add_in_condition` to prevent Oracle bind-variable name collision (`ORA-01006`).
- Evidence: `src/mes_dashboard/services/query_tool_service.py:2558-2567`, `src/mes_dashboard/sql/builder.py:23`

**Lesson B — `lot-equipment-lookup` response must include `lot_names`** — not promoted (evidence pointer imprecise; revisit as additive api-contract §lot-equipment-lookup response shape spec in a future change).

**Lesson C — QT-07 cross-station reject semantic** — already in `contracts/business/business-rules.md:QT-07`; no further action.

## Follow-up Work

- Tier 3 E2E tests require full implementation in
  `tests/e2e/test_query_tool_e2e.py` and `frontend/tests/playwright/query-tool.spec.js`
  before production promotion. Currently TODO scaffold only.
- Advisory UX items from ui-ux-reviewer (non-blocking):
  A-1: EQUIPMENTNAME column position (may be off-screen on narrow viewports)
  A-2: empty-state cannot distinguish no-lots-found vs no-rejects-for-lots
  A-3: mixed Chinese/English column headers vs LotRejectTable baseline
  A-4: truncation banner does not mention export is also truncated
  A-5: default sort missing WORKCENTERSEQUENCE_GROUP as explicit tie-breaker

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and
active project guidance (`CLAUDE.md`).
