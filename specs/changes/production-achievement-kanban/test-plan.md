---
change-id: production-achievement-kanban
schema-version: 0.1.0
last-changed: 2026-07-02
risk: high
tier: 1
---

# Test Plan: production-achievement-kanban

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 (page reachable, manifests wired) | e2e | tests/playwright/production-achievement.spec.js | 1 |
| AC-2 (shift_code PA-01/PA-02 boundaries) | unit | tests/test_production_achievement_shift_code.py | 0 |
| AC-3 (output_date PA-03/PA-04, 4/26-4/27 case) | unit | tests/test_production_achievement_output_date.py | 0 |
| AC-4 (PA-05 predicate + PA-06 grouping/formula) | unit | tests/test_production_achievement_service.py | 0 |
| AC-5 (workcenter_group via filter_cache reuse) | integration | tests/integration/test_production_achievement_filter_cache_reuse.py | 1 |
| AC-6 (target table CRUD, no date dim, mysql_client direct) | unit | tests/test_production_achievement_target_service.py | 0 |
| AC-6 (MySQL round-trip + OPS-disabled fallback) | integration | tests/integration/test_production_achievement_mysql_roundtrip.py | 1 |
| AC-7 (permission check allow/deny/fail-closed) | unit | tests/test_production_achievement_permissions.py | 0 |
| AC-7 (403 write path, admin whitelist endpoints) | contract | tests/test_production_achievement_routes.py | 1 |
| AC-7 (permission-gated edit e2e) | e2e | tests/playwright/production-achievement.spec.js | 1 |
| AC-8 (business-rules.md PA-01..PA-07 entries) | contract | contracts/business/business-rules.md (contract-reviewer check, not a test file) | n/a |

## Test Families Required

Mark all that apply: unit / contract / integration / e2e / data-boundary / resilience

| family | tier | notes |
|---|---|---|
| unit | 0 | shift_code boundary seconds (07:29:59/07:30:00/19:29:59/19:30:00, date cutoffs 20191231/20200330), output_date cross-midnight incl. 4/26->4/27 case, PA-05 predicate branch coverage (雙晶/三晶 exclusion + each SPECNAME/processtypename pair), PA-06/PA-07 achievement math (missing-target null, zero-target null, zero-output/nonzero-target=0.0), permission allow/deny/fail-closed, target CRUD service (upsert semantics) |
| contract | 1 | response-shape samples for all 6 endpoints in tests/contract/response-samples.json incl. PUT /api/production-achievement/targets 403 path; route-level per-kwarg forwarding assertions (test-discipline.md) for report/targets/permissions routes |
| integration | 1 | direct MySQL round-trip for both new tables via core/mysql_client.py; MYSQL_OPS_ENABLED=false fallback (read->null target, write->503); filter_cache.get_spec_workcenter_mapping() reuse (no new SPECNAME map introduced) |
| e2e | 1 | tests/playwright/production-achievement.spec.js -- navigate 生產輔助->生產達成率, filter (date/shift/workcenter_group), render table/chart; admin permission block assign/revoke; authorized vs unauthorized target-edit path |
| data-boundary | 1 | negative/non-numeric target_qty -> 400 VALIDATION_ERROR (must strictly exceed valid range, not equal boundary); unmapped SPECNAME excluded from grouped output; empty qualifying-row set -> empty rows array, not error; NULL/0 TRACKOUTQTY handling |
| resilience | 1 | MySQL unreachable / MYSQL_OPS_ENABLED=false: permission check fails closed (deny, never allow); report degrades to target_qty:null/achievement_rate:null, never 500; write endpoints return 503 not crash |
| monkey/fuzz | n/a | out of scope -- see below |
| stress/soak | n/a | out of scope -- see below |

### Test File / Case Index

- tests/test_production_achievement_shift_code.py -- test_two_shift_boundary_seconds, test_two_shift_date_cutoff_inclusive_exclusive, test_three_shift_window_boundary_seconds, test_three_shift_date_window_edges_20200101_20200329
- tests/test_production_achievement_output_date.py -- test_two_shift_n_tail_attributes_prev_day, test_two_shift_d_and_late_n_attribute_same_day, test_confirmed_0426_0427_cross_midnight_case, test_three_shift_c_tail_assumption_documented
- tests/test_production_achievement_service.py -- test_pa05_predicate_excludes_shuangjing_sanjing_rows, test_pa05_predicate_each_specname_processtype_pairing, test_grouping_by_output_date_shift_workcenter_group, test_workcenter_group_resolved_via_filter_cache_not_hardcoded, test_achievement_rate_missing_target_is_null, test_achievement_rate_zero_target_is_null_not_infinity, test_achievement_rate_zero_output_nonzero_target_is_zero, test_unmapped_specname_excluded_from_output, test_empty_qualifying_rows_yields_empty_result_not_error
- tests/test_production_achievement_target_service.py -- test_upsert_target_unique_key_shift_workcenter_group, test_negative_target_qty_rejected, test_non_numeric_target_qty_rejected, test_target_read_no_date_dimension
- tests/test_production_achievement_permissions.py -- test_whitelisted_user_allowed, test_non_whitelisted_user_denied, test_mysql_unreachable_fails_closed_deny, test_ops_disabled_fails_closed_deny, test_distinct_from_admin_required
- tests/test_production_achievement_routes.py -- per-kwarg forwarding for report/targets/permissions routes; test_put_targets_403_when_not_whitelisted, test_put_targets_503_when_mysql_ops_disabled, test_get_targets_no_permission_gate, test_admin_permissions_put_requires_admin
- tests/integration/test_production_achievement_mysql_roundtrip.py -- test_target_table_write_then_read_roundtrip, test_permission_table_write_then_read_roundtrip, test_mysql_ops_disabled_read_degrades_to_null, test_mysql_ops_disabled_write_returns_503
- tests/integration/test_production_achievement_filter_cache_reuse.py -- test_service_calls_get_spec_workcenter_mapping_not_new_cache
- tests/playwright/production-achievement.spec.js -- navigates from 生產輔助 drawer to 生產達成率, filters by date/shift/workcenter_group and renders table, admin assigns and revokes can_edit_targets, authorized user edits target value, unauthorized user blocked from editing target value
- tests/playwright/resilience/production-achievement-resilience.spec.js -- mysql unavailable degrades report to null achievement no 500, permission check denies when mysql unreachable
- tests/playwright/data-boundary/production-achievement-data-boundary.spec.js -- rejects negative target_qty input, rejects non-numeric target_qty input, empty result set renders empty state not error

## Test Execution Ladder

| phase | required | command source | max failures | result artifact |
|---|---:|---|---:|---|
| collect | yes | cdd-kit test select | 1 | test-runs/<run-id>/summary.json |
| targeted | yes | cdd-kit test select | 1 | test-evidence.yml |
| changed-area | yes | cdd-kit test select | 1 | test-evidence.yml |
| contract | if affected | cdd-kit validate | 1 | test-evidence.yml |
| quality | if configured | ci-gates.md | 1 | test-evidence.yml |
| full | final/CI | cdd-kit test run --phase full | 1 | test-evidence.yml |

## Test Update Contract

| existing test | action | reason |
|---|---|---|
| tests/test_permissions.py | extend | add new can_edit_targets check alongside existing is_admin tests; do not duplicate the module, add new test functions for the new independent gate |

No existing test's expected behavior changes (additive feature, no existing endpoint/report modified).

## Stop Rules

- Do not run broad pytest before targeted and changed-area phases pass.
- Do not investigate more than the first failure per phase.
- Do not classify any failure as known, pre-existing, waived, or allowed.
- If full suite fails, record the first failure and block the gate.

## Out of Scope

- Monkey/fuzz testing -- not a high-fuzz surface (change-classification.md); malformed target_qty input covered under data-boundary instead.
- Stress/soak testing -- explicit non-goal: not an auto-refresh/big-screen kanban, no new queue/long-running/high-load surface (change-classification.md, ci-gate-contract.md).
- Three-shift (A/B/C) output_date cross-day rule (PA-04) production-data verification -- documented as unverified assumption only, not an acceptance target (change-request.md Non-goals).
- CSS visual regression -- caught by existing css-governance gate (Rule 6); routine evidence via agent-log/visual-reviewer.yml, no dedicated test file.

## Notes

New CSS scoping (`.theme-production-achievement`) is caught by the existing `css-governance` gate per ci-gate-contract.md -- no new test file needed. Correction: all Playwright spec paths in this plan and in ci-gate-contract.md's registered `playwright-critical-journeys` command are relative to `frontend/` (the gate command runs `cd frontend && npx playwright test tests/playwright/...`) -- the actual files live under the existing `frontend/tests/playwright/`, `frontend/tests/playwright/resilience/`, and `frontend/tests/playwright/data-boundary/` directories, not a new repo-root `tests/playwright/` tree.
