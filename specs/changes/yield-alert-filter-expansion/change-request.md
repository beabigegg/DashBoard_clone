# Change Request

## Original Request

> 在製程類型選擇中加入
> 重工(GD%)
> 委外(F%)
> WIP(W%)
> 其他(D%)
> 這幾個選項
>
> 然後快取內篩選的 站別群組 改為跟其他FILTER依樣, 直接設定為從DUCKDB的DEPARTMENT_NAME獲取

(verbatim, translated context added by assistant below)

## Business / User Goal

Affected surface: `yield-alert-center` 頁面的「製程類型」選擇器（目前僅 GA%/GC% 兩選項）；以及該頁 filter-options / cross-filter-options API 回傳的「站別群組」(workcenter_groups) 選項來源。

Desired behavior change:
1. 製程類型選擇器新增 4 個選項：重工 (`GD%`)、委外 (`F%`)、WIP (`W%`)、其他 (`D%`)，讓使用者可查詢目前完全不可見的 ~1.65%（近 6 個月約 26,565 筆）交易資料（`WIP_ENTITY_NAME` 前綴 GD/F2/FA/FB/D2/W2，對應 `WIP_CLASS_CODE` = 重工RW/委外/PJ_NST_A）。
2. `workcenter_groups`（站別群組）篩選來源從目前獨立於 query_id/process_type 的全域 `filter_cache`（讀 `DWH.DW_MES_SPEC_WORKCENTER_V`）改為與其他 filter 欄位（lines/packages/types/functions）一致：直接對該 `query_id` 對應的 DuckDB spool 檔案的 `DEPARTMENT_NAME` 欄位做 `SELECT DISTINCT`。

Observable success criterion (assistant-inferred, given the request's technical precision):
- 前端「製程類型」下拉/切換元件顯示 6 個選項（原 GA/GC + 新增 4 個），選擇後可成功觸發 `POST /api/yield-alert/query` 並以對應 `LIKE` pattern 產生新 `query_id`/spool。
- `GET /api/yield-alert/view` 與 `GET /api/yield-alert/cross-filter-options` 回傳的站別群組選項改為該 query_id spool 內 `DEPARTMENT_NAME` 的 distinct 值（不再讀取全域 `filter_cache`/`DW_MES_SPEC_WORKCENTER_V`），且會隨 process_type 切換而變動，與 lines/packages/types/functions 的行為一致。

## Non-goals

- 不重新設計「良率」(`yield_pct`) 的計算邏輯本身。
- 不處理 GA 內部混雜的 10 種 `WIP_CLASS_CODE`（量產/代工/樣品/工程/餘晶/已驗證/久存/WIP/試量產/打帶跑）的細分——GA 仍以單一選項處理。
- 不移動或棄用 `filter_cache.get_workcenter_groups()`（其他頁面可能仍在使用），僅讓 yield-alert-center 改為使用 spool 內的 DEPARTMENT_NAME。

## Constraints

- `process_type` 目前是 `query_id` 雜湊輸入之一且用於 Oracle `WHERE ... LIKE :process_type`（`yield_alert_dataset_cache.py` `_PRIMARY_DETAIL_SQL`），新增選項需維持相同機制（前綴 LIKE pattern），新 pattern 需與現有 GA%/GC% 互斥（例如 `F%` 需確認不會誤配 GA/GC/其他前綴）。
- 前端切換 process_type 現有「清空 query_id + 強制重新查詢」的行為（`App.vue` 約 line 803-824）須套用到新選項。
- `workcenter_groups` 站別群組分組/排序邏輯（`_YIELD_WORKCENTER_GROUP_ORDER`、`_DEPT_SEQ_MAP`，`yield_alert_dataset_cache.py` 附近）需確認如何對應到 spool 的原始 `DEPARTMENT_NAME` 值——需要先弄清楚現有分組邏輯是否仍要保留分組顯示名稱，或改為顯示 spool 內 raw DEPARTMENT_NAME。

## Known Context

- 已透過直接查詢 Oracle `DWH.ERP_WIP_MOVETXN` 確認（近 6 個月資料）：`WIP_ENTITY_NAME` 前綴共 8 種（GA/GC/GD/F2/FB/FA/D2/W2），`WIP_CLASS_CODE` 共 14 種；除 GA 外其餘前綴幾乎一對一對應單一 WIP_CLASS_CODE：GC→點測、GD→重工RW、F2/FA/FB→委外、D2→PJ_NST_A、W2→量產(390)+PJ_NST_A(9)。
- 已確認 `process_type` 是 `query_id` 的雜湊輸入之一（`yield_alert_routes.py` line ~178-185），GA/GC 切換會產生不同 query_id 與不同 spool 檔案。
- 已確認 filter-options 分兩種來源：`workcenter_groups` 走全域 `filter_cache`（與 query_id 無關）；`lines`/`packages`/`types`/`functions`/`process_categories` 走 `_query_filter_options()` / `compute_cross_filter_options()` 對 query_id spool 做 `SELECT DISTINCT`（`yield_alert_sql_runtime.py`）。

## Open Questions

- `其他 (D%)` 選項名稱是否恰當？D2 前綴目前對應 `WIP_CLASS_CODE = PJ_NST_A`，並非語意上的「其他」，待確認 UI 標籤是否需要更貼近業務語意的命名（例如「特殊專案」）。

## Resolved Decisions

- 使用者指示「快取內篩選的站別群組改為跟其他FILTER依樣」= 站別群組改為與 `lines`/`packages`/`types`/`functions` 完全相同的機制：對 query_id 對應的 spool 做 `SELECT DISTINCT DEPARTMENT_NAME`，不再套用 `_YIELD_WORKCENTER_GROUP_ORDER`/`_DEPT_SEQ_MAP` 分組顯示邏輯，也不再讀取全域 `filter_cache`/`DW_MES_SPEC_WORKCENTER_V`。回傳值即為 spool 內 raw `DEPARTMENT_NAME` 字串。

## Requested Delivery Date / Priority

未指定；使用者於同一互動 session 中連續要求，屬於快速迭代開發節奏。
