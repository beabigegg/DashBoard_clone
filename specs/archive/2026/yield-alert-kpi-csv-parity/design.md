# Design: yield-alert-kpi-csv-parity

## Summary
The yield-alert-center KPI summary cards ("移轉量"/"報廢量") aggregate a broader
scope than the detail list/CSV export, so users cannot reconcile the CSV totals
against the cards. Source inspection corrects the change-request's root-cause
text: `_query_summary()` is already invoked with `full_where` (all 6 dimension
filters, `dept_proc_only=False`, see `yield_alert_sql_runtime.py:897-907`), so
the dimension-filter gap is already closed. The remaining divergence is that the
summary does NOT apply the alert-candidate predicate (`SCRAP_QTY <> 0` and the
`NOT (yield_pct >= risk_threshold AND scrap_qty < min_scrap_qty)` exclusion) that
`_query_alerts()` applies. This change rescopes the top-level KPI summary to the
alert-candidate set, guarantees `transaction_qty` is deduped over the
non-REASON_CODE dimension so multi-reason groups are not double-counted, wires
`risk_threshold`/`min_scrap_qty` through the `/summary` route (currently dropped),
fixes the CSV float-noise bug, and records the scope as business rule YA-13.

## Affected Components
| component | file path(s) | nature of change |
|---|---|---|
| KPI summary query | `src/mes_dashboard/services/yield_alert_sql_runtime.py` (`_query_summary` 196-240; reuse `_query_alerts` CTE 554-611) | rescope to alert-candidate set via shared CTE builder; accept `risk_threshold`/`min_scrap_qty` |
| View orchestration | `yield_alert_sql_runtime.py` (`try_compute_view_from_spool` 901-951) | pass threshold params into `_query_summary` |
| Summary route wiring | `src/mes_dashboard/routes/yield_alert_routes.py` (`api_yield_alert_summary` 402-440) | forward `risk_threshold`/`min_scrap_qty` (today defaults only) |
| Cache passthrough | `src/mes_dashboard/services/yield_alert_dataset_cache.py` (`apply_view` 891-937) | no signature change; already threads both params to runtime |
| CSV export | `frontend/src/yield-alert-center/App.vue` (`_buildAlertsCSV` 643-660) | round `toPcs(transaction_qty)`/`toPcs(scrap_qty)` to whole pcs |
| Business contract | `contracts/business/business-rules.md` (YA-13) | new rule: KPI scope = alert-candidate + tx-dedup dimension |
| API/data contracts | `contracts/api/api-contract.md`, `contracts/data/data-shape-contract.md`, `contracts/CHANGELOG.md` | summary-value semantics note; CSV rounded-pcs formatting |

## Key Decisions

**Decision 1 — Reuse the `_query_alerts` `alerts_filtered` CTE chain (option b).**
The new KPI totals must be computed from the SAME two-level CTE chain
(`_tx_daily` → `tx_lookup` → `alert_groups` → `alert_with_tx` → `alerts_computed`
→ `alerts_filtered`) that `_query_alerts()` already builds, by factoring that CTE
SQL into a shared builder and appending
`SELECT COALESCE(SUM(transaction_qty),0), COALESCE(SUM(scrap_qty),0) FROM
(SELECT DISTINCT <tx-dedup dims>, transaction_qty FROM alerts_filtered)` for the
tx side and `SUM(scrap_qty) FROM alerts_filtered` for the scrap side.
Rationale: parity is guaranteed *by construction* — the KPI reads the exact rows
the CSV exports, so no future edit can silently drift two independently
maintained WHERE clauses out of sync (the recurring failure mode in this file per
CLAUDE.md "SQL CTE changes: update both locations"). Rejected alternative (a),
rebuilding an independent WHERE clause in `_query_summary` mirroring
`_query_alerts`'s predicate: rejected because it re-creates exactly the
dual-maintenance drift that caused this bug, and would require re-deriving the
threshold/risk-level logic a second time. Cost note: the shared CTE is already
executed for the alerts count/page; a second lightweight aggregate over
`alerts_filtered` reuses the same scan pattern rather than adding the summary's
current separate two-subquery scan — no net extra full table scan.

**Decision 2 — tx-dedup dimension = `_query_alerts`'s `tx_extra_cols` (+ bucketed DATE_BUCKET), NOT the module-level `_TX_DEDUP_COLS`.**
Because Decision 1 sums `transaction_qty` values that are already materialized by
the `tx_lookup` CTE keyed on `tx_extra_cols` (`WORKORDER, DEPARTMENT_GROUP,
PROCESS_CATEGORY, LINE_NAME, PACKAGE_NAME, TYPE_NAME, FUNCTION_NAME,
OPERATION_TEXT` + bucketed `DATE_BUCKET`, see 534-538), the DISTINCT/dedup for the
KPI SUM must use that identical key set. `_TX_DEDUP_COLS` (35-39) additionally
includes `DEPARTMENT_NAME` (the raw workcenter, finer than the normalized
`DEPARTMENT_GROUP`); using it would dedup on a finer key than the CTE produced,
so a single `tx_lookup` value spanning multiple `DEPARTMENT_NAME`s would fail to
split and the DISTINCT would keep one copy — breaking parity with the CSV, whose
`transaction_qty` column is the `tx_lookup` value. This is the concrete
correctness reason the general "prefer the shared constant" preference is
overridden here: the constant is incompatible with the CTE this KPI is built on.
Do not introduce a third variant. **This is the definitive statement for YA-13:
KPI `transaction_qty` = SUM over DISTINCT (`WORKORDER`, `DEPARTMENT_GROUP`,
`PROCESS_CATEGORY`, `LINE_NAME`, `PACKAGE_NAME`, `TYPE_NAME`, `FUNCTION_NAME`,
`OPERATION_TEXT`, bucketed `DATE_BUCKET`) of the alert-candidate set;
`scrap_qty` = plain SUM (already REASON_CODE-grouped, no dedup needed).**

**Decision 3 — Scope limited to the top-level KPI summary cards only; trend/heatmap/station/package summaries stay on their current scope.**
trend/heatmap/station/package are visualizations whose per-bucket/per-station
values users do not manually reconcile against a row-level CSV export, and they
share the current broader (non-threshold) scope consistently among themselves.
Rescoping them to alert-candidate is a larger blast radius (changes visible chart
values, station rankings) with no reconciliation-parity payoff and is explicitly
OUT of scope. This is recorded as a documented non-goal, not a silent gap: YA-13
must state the KPI-summary-only boundary, and a follow-up note captures the option
to revisit trend/heatmap scoping if a future reconciliation need arises.

**Decision 4 — CSV rounds `toPcs()` to whole pcs via `Math.round`.**
Oracle K-PCS values are exact multiples of 0.001 (= 1 pcs, per `utils.ts:1-3`), so
one pcs is the true data granularity and `Math.round(toPcs(v))` discards only the
binary-float residue introduced by DuckDB DOUBLE SUM/ROUND (e.g.
`4011.9999999999995` → `4012`). No legitimate sub-pcs precision exists to lose.
This matches the on-screen table, which already hides the noise via
`toPcs().toLocaleString()` (App.vue:1159-1160). Rejected: `.toFixed(3)` parity
with yield_pct/risk_score — rejected because it would preserve fractional pcs that
are pure float noise, not real data.

## Migration / Rollback
No schema, spool, or data migration: this changes in-memory DuckDB aggregation and
one frontend formatter only. The `GET /api/yield-alert/view` and `/summary`
response shapes are unchanged; only summary numeric values change. Contract samples
(`get_yield_alert_view.json`, `get_yield_alert_summary.json`) will regenerate with
new summary values — regenerate both `contracts/openapi.json` and
`contracts/api/openapi.json` only if schema changes (none expected here). Rollback
is a straight code revert of the runtime, route, and Vue changes plus the YA-13
contract entry; because no spool is rewritten, reverting needs no cache purge or
re-warm. Feature flag `YIELD_ALERT_SQL_VIEW_ENABLED` already gates the SQL path;
if the rescoped KPI regresses, disabling it falls back to the legacy path.

## Open Risks
- `.cdd/code-map.yml` shows as modified (uncommitted) in git status; ranges cited
  here were verified by direct source reads, not the map.
- The `/summary` route currently drops `risk_threshold`/`min_scrap_qty`; after
  Decision 1 rescopes the summary, that route MUST forward them or the two routes
  will return different KPI numbers for the same query. Flagged for backend-engineer
  as a required wiring change, not optional.
- Change-request root-cause text overstates the dimension-filter gap (claims
  `dept_proc_where` only); real gap is threshold/`SCRAP_QTY<>0` predicate. Tests
  must assert the actual predicate, not the stale description.
