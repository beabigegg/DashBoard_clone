# QA Report: yield-alert-filter-expansion

## Verdict

**ready-with-known-risks** (approved-with-risk). No blocking issues. All 8 acceptance criteria (AC-1..AC-8) verified against source and tests, not just agent-log claims (5 spot-checked directly). All required `test-evidence.yml` phases (collect, targeted, changed-area, contract) passed; qa-reviewer independently re-ran targeted and changed-area suites and results matched recorded evidence exactly.

## Scope discipline confirmed

`filter_cache.py` and `config/workcenter_groups.py` not modified (git-confirmed empty diff). `GET /api/yield-alert/filter-options` route body unchanged (AC-8/YA-11 regression guard holds — still calls `get_yield_workcenter_group_options()`). All 20 touched paths fall within `context-manifest.md` Allowed Paths.

## Agent-concern reconciliation

Every concern raised earlier in this change was verified fixed at source, not just acknowledged:
- contract-reviewer Pitfall #1 (raw `DEPARTMENT_NAME` vs normalized `DEPARTMENT_GROUP`) — respected, with a discriminating test that would fail if the wrong column were used.
- contract-reviewer Pitfall #2 (net-new dimension, not a re-point) — respected; additive 5th `dim_spec` tuple, all existing specs' `other_filter_keys_to_apply` extended.
- implementation-planner IP-2/IP-5 confirm-only scope — honored; `yield_alert_dataset_cache.py` untouched.
- DuckDB-WASM parity risk (§3.16.6) — closed by `useYieldAlertDuckDB.ts` matching dimension.

## Known risks (residual, non-blocking)

1. **Playwright `yield-alert-center.spec.ts` not CI-wired** — pre-existing gap (ci-gates.md §Merge Eligibility), not introduced or widened by this change. Extended AC-1/AC-4 assertions pass locally but do not run in any CI workflow. Recommended follow-up: wire the spec into `frontend-tests.yml` (same pattern as `mid-section-defect.spec.ts`).
2. **Three pre-existing, unrelated failures/mismatches noted during review** — confirmed genuinely pre-existing (unchanged lines / files untouched by this diff), not this change's responsibility to fix:
   - `tests/test_runtime_hardening.py::test_health_reports_pool_saturation_degraded_reason` — unrelated health-endpoint assertion, zero yield-alert coupling.
   - Playwright `test_page_loads_with_filter_panel` — asserts a `[data-testid="clear-btn"]` that has never existed in `App.vue`.
   - `App.vue:91` labels `GA%` as `封裝`, while `change-request.md`/`business-rules.md` YA-02/YA-02a consistently call it `量產` — pre-existing label/contract wording mismatch, one line above the `D%` label this change did fix.

## Follow-up recommendations (non-blocking, out of this change's scope)

- Open a tracked change to wire `yield-alert-center.spec.ts` into CI.
- Open a tracked change for the pre-existing `封裝`/`量產` label mismatch and the `test_runtime_hardening` health-string assertion.
- Invoke `spec-drift-auditor` at the next release-gate cadence per standing practice.
