# Change Request

## Original Request

reject-history 主查詢加入 Type/Package/Function 前置篩選（Oracle BASE_WHERE 層），讓使用者在日期區間查詢前就能縮減資料量

## Business / User Goal

使用者在 reject-history 頁面查詢時，若能在送出 Oracle 查詢前就指定 Type / Package / Function，Oracle 在執行 `reject_raw` CTE 的 GROUP BY 之前就能過濾原始行數，大幅減少資料傳輸量與計算時間。特別是在放寬查詢區間至 365 天後，此優化更為重要。

## Non-goals

- PJ_BOP：`performance_daily_lot.sql` 未包含此欄，略過
- 不改動補充篩選（DuckDB 快取層）現有邏輯
- 不變更 cross-filter 選項演算法（沿用 container_filter_cache 4-tuple 機制）

## Constraints

- 過濾條件必須注入 `{{ BASE_WHERE }}` 層（在 reject_raw CTE WHERE 子句），而非 `{{ WHERE_CLAUSE }}` 層（後者在 Oracle CTE 物化後才執行，無法減少 GROUP BY 前的資料量）
- PJ_TYPE / PJ_FUNCTION / PRODUCTLINENAME 來自 `DWH.DW_MES_CONTAINER c`（LEFT JOIN），需以 `NVL(TRIM(c.XXX), '(NA)')` 形式寫條件，避免 NULL 值漏失
- Filter options 沿用既有 `container_filter_cache`（production-history 共用），不另建快取
- 三個 MultiSelect 位於 FilterPanel 主查詢區段（和日期區間同層），空選 = 不限制

## Known Context

- `performance_daily_lot.sql` 已有 `{{ BASE_WHERE }}` placeholder，目前只填入日期條件（`_DEFAULT_BASE_WHERE`）
- `_prepare_sql()` 已有 `base_where: str = ""` 參數，可直接擴充
- `container_filter_cache.get_filter_options(selected)` 提供 cross-filter 4-tuple 選項（pj_types, packages, bops, pj_functions）
- production-history 的 `/api/production-history/filter-options` endpoint 已是現成的 cross-filter API，可在 reject-history 前端直接呼叫

## Open Questions

（無）

## Requested Delivery Date / Priority

High — 與 365 天區間優化同期功能
