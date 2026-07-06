# Archive: yield-alert-kpi-csv-parity

## Change Summary
The yield-alert-center KPI cards ("移轉量"/"報廢量") aggregated a broader scope
(all rows matching date/dimension filters) than the detail list and its CSV
export (only alert-candidate rows: `SCRAP_QTY <> 0` and NOT within the
risk-threshold/min-scrap-qty exclusion), so users could not reconcile CSV totals
against the KPI cards. Separately, the CSV export wrote raw floating-point
values for `transaction_qty`/`scrap_qty` (e.g. `4011.9999999999995`) that Excel
sometimes treats as text, silently breaking `SUM()`. This change rescoped the
KPI summary query to the same alert-candidate set as the CSV/list (via a shared
CTE builder, deduping `transaction_qty` over the non-REASON_CODE dimension to
avoid double-counting multi-reason groups), wired `risk_threshold`/`min_scrap_qty`
through the `/summary` route, and rounded the CSV's `transaction_qty`/`scrap_qty`
fields to whole pcs at the formatting call site.

## Final Behavior
- `GET /api/yield-alert/summary` now computes "移轉量"/"報廢量" from the same
  `alerts_filtered` CTE chain that backs the alert list/CSV, applying
  `risk_threshold`, `min_scrap_qty`, `SCRAP_QTY <> 0`, and all 6 dimension
  filters — previously it summed the full filtered scope with none of those
  predicates.
- `transaction_qty` in the KPI total is deduped on `_TX_EXTRA_COLS` (+
  `DATE_BUCKET`) before summing, preventing double-counting when a single
  workorder/date/dept group has multiple `REASON_CODE` rows.
- `api_yield_alert_summary` now parses and forwards `risk_threshold`/
  `min_scrap_qty` from request args (previously dropped, defaults only).
- CSV export (`_buildAlertsCSV` in `App.vue`) now wraps
  `toPcs(transaction_qty)`/`toPcs(scrap_qty)` in `Math.round(...)`, eliminating
  binary floating-point residue from the output file. The on-screen table's
  `.toLocaleString()` display path and `yield_pct`/`risk_score` formatting were
  untouched.
- Response shapes for `/api/yield-alert/view` and `/api/yield-alert/summary`
  are unchanged (value-semantics-only change) — verified by
  `test_view_and_summary_response_shape_unchanged_after_scope_unification`.

## Final Contracts Updated
- `contracts/business/business-rules.md` — new rule **YA-13**: KPI summary
  scope = alert-candidate set, tx-dedup dimension documented (business
  1.39.0 → 1.40.0).
- `contracts/data/data-shape-contract.md` — new subsection **§3.16.7** (Alerts
  CSV Numeric Export Formatting): `transaction_qty`/`scrap_qty` rounded to
  whole pcs (data 1.32.0 → 1.33.0).
- `contracts/CHANGELOG.md` — entries for business 1.40.0 and data 1.33.0.
- `contracts/api/api-contract.md` — **deliberately deferred**: the
  contract-write hook blocks direct prose edits (`CDD_CONTRACT_WRITE_STRICT=1`),
  and `cdd-kit contract endpoint set` only mutates table cells, not prose
  Compatibility Notes. No endpoint shape/request/response schema changed, so
  there was nothing for `set` to mutate. User chose to defer this
  documentation addition (ADR 0004 SS7 will extend `set` to prose sections
  later) rather than loosen the hook. YA-13 + data-shape-contract §3.16.7
  fully document the value-semantics change in the meantime.

## Final Tests Added / Updated
- `tests/test_yield_alert_sql_runtime.py::TestQuerySummaryAlertScopeParity`
  (4 tests): documents the double-count trap, department-name-split dedup
  safety, shared-CTE-builder structural assertion, and threshold-forwarding.
- `tests/test_yield_alert_routes.py`: `test_summary_route_forwards_risk_threshold_and_min_scrap_qty`,
  `test_summary_route_uses_default_thresholds_when_absent`,
  `test_view_and_summary_response_shape_unchanged_after_scope_unification`.
- `tests/test_yield_alert_service.py::TestKpiCsvReconciliation::test_summary_and_alerts_reconcile_end_to_end_with_multi_reason_group`.
- `tests/test_yield_alert_contracts.py::TestBusinessRuleYA13` (2 tests): YA-13
  wording + changelog version-entry presence (business/data only, api
  deliberately excluded).
- `frontend/tests/yield-alert/App.csv-export.test.js` (bug-fix-engineer,
  pre-existing as regression baseline): float-residue reproduction case +
  whole-pcs rounding assertion.
- Full suite at gate time: 96 backend + 16 frontend tests passed (qa-reviewer
  independent re-run); ruff and vue-tsc clean.

## Final CI/CD Gates
No new CI/CD surface. Reused existing required gates per `ci-gates.md`: lint
(ruff), type-check (vue-tsc), backend unit/integration (pytest, targeted
yield-alert files), frontend unit (vitest), contract (`pytest
tests/test_yield_alert_contracts.py` + `cdd-kit validate --contracts`),
integration (`TestKpiCsvReconciliation`), data-boundary (double-count/dedup/
float-residue cases). E2E-critical deferred as optional at Tier 2. No
nightly/weekly/manual gates required (no new load/concurrency/real-infra
surface). Rollback is a straight code revert; `YIELD_ALERT_SQL_VIEW_ENABLED`
flag remains the kill switch back to the legacy `query_alert_candidates()` path.

## Production Reality Findings
- qa-reviewer found a **benign log inaccuracy**: `backend-engineer.yml` claimed
  it edited existing stale assertions, but `git diff` showed the test-file
  changes were purely additive (0 deletions) — no test-weakening occurred, just
  an inaccurate log entry, not a defect.
- Confirmed the `api-contract.md` deferral is legitimate (no endpoint
  shape/request/response schema actually changed) rather than a corner cut.
- Working tree at gate time also contained the concurrent
  `eap-alarm-coarse-filter` change sharing `business-rules.md`/`CHANGELOG.md`;
  this change's contract entries were verified intact and isolated at commit
  time via a HEAD-reconstructed-blob staging technique (see Lessons below).

## Lessons Promoted to Standards
Reviewed by `contract-reviewer` (Step 3 audit); all three approved as evidence-backed, non-duplicative refinements/additions to the `cdd-kit:learnings` region of `CLAUDE.md` plus their backing docs:

1. **`cdd-kit contract endpoint set` prose-section gap** — new entry in `docs/cdd-kit-patterns.md` ("`cdd-kit contract endpoint set` — Table Cells Only, Not Prose Sections") + new `CLAUDE.md` bullet under "CDD Kit operations". Evidence: `tasks.yml` task 2.1; `archive.md` Final Contracts Updated.
2. **Git-staging technique for concurrent contract-version bumps** — extended the existing "Version-Skip Gate" section in `docs/cdd-kit-patterns.md` with option (c) (`git update-index` against a HEAD-reconstructed blob); edited the existing `CLAUDE.md` bullet in place (no net new line). Evidence: `tasks.yml` task 6.1 note.
3. **Shared CTE builder for cross-function parity** — new subsection in `docs/architecture/service-patterns.md` ("Shared CTE Builder for Cross-Function Parity"); edited the existing `CLAUDE.md` "SQL CTE changes" bullet in place (no net new line). Evidence: `design.md` Decision 1; `test_summary_and_alerts_share_the_same_cte_builder`.

Rejected as not durable/generalizable: the qa-reviewer log-vs-diff discrepancy (one-off log-accuracy note), the "trap-documenting" test-naming pattern (single instance, not a new discipline), and the route-parameter-forwarding bug (one-off, already implicit in existing test-discipline guidance).

Net `CLAUDE.md` growth: +1 line (unavoidable, no existing line covered the contract-endpoint-set gap); 2 other lines edited in place at net 0 growth. `cdd-kit validate --contracts` and `cdd-kit context-scan` both re-ran clean after these doc-only edits (no `contracts/` schema-version bump required — no product-behavior facts changed, only process documentation).

## Follow-up Work
- `contracts/api/api-contract.md` Compatibility Notes / CHANGELOG entry for
  this change is deferred until ADR 0004 SS7 extends `cdd-kit contract endpoint
  set` to mutate prose sections (not just table cells).
- E2E-critical Playwright spec for the KPI/CSV reconciliation flow was
  explicitly out of scope for Tier 2 and not authored.

## Cold Data Warning
This archive is historical evidence. Current requirements live in `contracts/`
and active project guidance (`CLAUDE.md`).
