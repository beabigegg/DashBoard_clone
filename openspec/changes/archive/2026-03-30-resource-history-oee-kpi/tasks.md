## 1. Backend SQL

- [x] 1.1 Create `sql/resource_history/oee_facts.sql` — Oracle query joining LOTWIPHISTORY (production) + LOTREJECTHISTORY (NG) via compound key (CONTAINERID+SPECNAME+WORKCENTERNAME), output EQUIPMENTID × SHIFT_DATE × TRACKOUT_QTY × NG_QTY
- [x] 1.2 Validate oee_facts.sql against verification data (GDBJ-0088 2026-03-05: TRACKOUT=250,199 NG=2,322) — PASS (fixed NG fan-out bug: partial trackout dedup for compound key join)

## 2. Backend Cache Pipeline

- [x] 2.1 Modify `resource_dataset_cache.py` — add parallel Oracle query for oee_facts.sql alongside base_facts.sql, write OEE results to second Parquet spool (prefix `resource_oee`); follow canonical base dataset pattern (spool key = date_range + granularity only); long date ranges use `batch_query_engine` for both queries
- [x] 2.2 Add `_empty_kpi()` fields: `oee_pct`, `yield_pct`, `trackout_qty`, `ng_qty`
- [x] 2.3 Update `make_canonical_base_query_id()` to also cover OEE spool namespace, or add parallel `make_canonical_oee_query_id()` with same key strategy

## 3. Backend DuckDB Runtime

- [x] 3.1 Modify `resource_history_sql_runtime.py` — register OEE spool as `oee_src` DuckDB view
- [x] 3.2 Modify `_query_kpi()` — LEFT JOIN oee_src, compute yield_pct and oee_pct
- [x] 3.3 Modify `_query_trend()` — LEFT JOIN oee_src by EQUIPMENTID+SHIFT_DATE, add oee_pct/yield_pct per period
- [x] 3.4 Modify `_query_heatmap()` — LEFT JOIN oee_src, add oee_pct/availability_pct per cell for metric toggle
- [x] 3.5 Modify `_query_detail()` — LEFT JOIN oee_src by EQUIPMENTID, add oee_pct/yield_pct/trackout_qty/ng_qty per resource

## 4. ~~Backend Pandas Fallback~~ — REMOVED (Phase 5 retired pandas fallback; DuckDB is sole path)

## 5. Backend CSV Export

- [x] 5.1 Modify `export_csv()` in resource_history_service.py — add OEE%, Yield%, TRACKOUT_QTY, NG_QTY columns after AVAIL%

## 6. Frontend Compute

- [x] 6.1 Add `calcYieldPct(trackout, ng)` and `calcOeePct(availability, yield)` to `core/compute.js`
- [x] 6.2 Update `buildResourceKpiFromHours()` to include OEE fields when available

## 7. Frontend KPI Cards

- [x] 7.1 Modify `KpiCards.vue` — add OEE% SummaryCard between OU% and AVAIL% (9 → 10 cards)

## 8. Frontend Trend Chart

- [x] 8.1 Modify trend chart component — add OEE% line with distinct color, update legend

## 9. Frontend Heatmap

- [x] 9.1 Add metric toggle dropdown to heatmap component (OU% / OEE% / AVAIL%, default OU%)
- [x] 9.2 Wire dropdown selection to switch heatmap cell values without additional API call

## 10. Frontend Detail Table

- [x] 10.1 Add OEE% column to detail table between OU% and AVAIL%
- [x] 10.2 Display "—" for resources with no production data (trackout + ng = 0)

## 11. Contract Updates

- [x] 11.1 Update `contract/api_inventory.md` if any API endpoints are added or modified — no update needed (response shape changes are additive/backward-compatible, no new endpoints)
