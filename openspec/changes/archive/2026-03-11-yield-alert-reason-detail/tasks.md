## 1. SQL — reason_detail.sql

- [x] 1.1 新增 `src/mes_dashboard/sql/yield_alert/reason_detail.sql`，以 `UPPER(TRIM(:workorder))` + `TO_DATE(:date_bucket, 'YYYY-MM-DD')` 為 filter，查詢 `DWH.DW_MES_LOTREJECTHISTORY`
- [x] 1.2 回傳欄位：`TXN_DATE`, `CONTAINERNAME`, `WORKCENTERNAME`, `LOSSREASONNAME`, `LOSSREASON_CODE`, `REJECTCOMMENT`, `REJECT_QTY`, `REJECT_TOTAL_QTY`（= REJECTQTY + STANDBYQTY + QTYTOPROCESS + INPROCESSQTY + PROCESSEDQTY，NVL 處理）
- [x] 1.3 ORDER BY `WORKCENTERNAME ASC, REJECT_TOTAL_QTY DESC, CONTAINERNAME ASC`；加 `FETCH FIRST 200 ROWS ONLY`

## 2. Backend Service — query_reason_detail()

- [x] 2.1 在 `src/mes_dashboard/services/yield_alert_service.py` 新增 `query_reason_detail(*, workorder: str, date_bucket: str) -> list[dict]`
- [x] 2.2 使用 `SQLLoader.load("yield_alert/reason_detail")` 載入 SQL，以 `read_sql_df_slow` 執行
- [x] 2.3 空值防衛：`workorder` 或 `date_bucket` 為空時直接 return `[]`
- [x] 2.4 將 DataFrame rows 轉為 dict list，`TXN_DATE` 欄位格式化為字串 `[:10]`；數值欄位以 `_safe_float` 處理

## 3. Backend Route — /api/yield-alert/reason-detail

- [x] 3.1 在 `src/mes_dashboard/routes/yield_alert_routes.py` import `query_reason_detail`
- [x] 3.2 新增 `GET /api/yield-alert/reason-detail` endpoint，加 `@_QUERY_RATE_LIMIT`
- [x] 3.3 validate: `workorder` 和 `date_bucket` 均必填，缺任一 → HTTP 400 `{ success: false, error: "缺少必要參數: workorder, date_bucket" }`
- [x] 3.4 feature flag 檢查：`_YIELD_ALERT_ENABLED` 為 False → HTTP 404
- [x] 3.5 呼叫 `query_reason_detail`，回傳 `{ success: True, data: { items: [...], workorder: ..., date_bucket: ... } }`；exception → HTTP 500

## 4. Frontend — State & Logic (App.vue)

- [x] 4.1 移除 `drilldownLoadingKey` ref、`linkageWarning` ref
- [x] 4.2 新增 `expandedRowKey = ref('')`、`reasonDetailRows = ref([])`、`reasonDetailLoading = ref(false)`
- [x] 4.3 移除 `openDrilldown()` function；新增 `toggleReasonDetail(row)` function：
  - 同一列再次點擊 → 清空 `expandedRowKey`（收合）
  - 不同列點擊 → 設定 `expandedRowKey`，呼叫 `GET /api/yield-alert/reason-detail`，結果存 `reasonDetailRows`
- [x] 4.4 移除 `buildDrilldownNotice` import（確認無其他使用），移除 `navigateToRuntimeRoute` import
- [x] 4.5 `resetFilters()` 新增清空 `expandedRowKey`、`reasonDetailRows`

## 5. Frontend — Template (App.vue)

- [x] 5.1 告警表格 `<thead>` 移除「映射狀態」`<th>` 欄位
- [x] 5.2 告警表格 `<tbody>` 每列移除 `match_status` `<td>` 與 `match-pill` span
- [x] 5.3 操作欄按鈕改為「查看原因」/「載入中...」/「收合」，`@click="toggleReasonDetail(row)"`
- [x] 5.4 在每個 `<tr v-for="row">` 後接 `<tr v-if="expandedRowKey === rowKey" class="reason-detail-row">`：
  - 子表格 colspan 跨所有欄位（8 欄）
  - `v-if="reasonDetailLoading"` → 顯示「載入中...」
  - `v-else-if="reasonDetailRows.length === 0"` → 「找不到對應的 MES 報廢明細」
  - `v-else` → 子表格顯示：LOT號、站別、報廢原因、原因代碼、報廢量、備註

## 6. Frontend — CSS (style.css)

- [x] 6.1 新增 `.reason-detail-row td` 樣式：淺色背景（`#f8f9fb`）、`padding: 0`（內層 table 自帶 padding）
- [x] 6.2 新增 `.reason-sub-table`：`width: 100%; font-size: 12px; border-collapse: collapse; margin: 8px 16px; width: calc(100% - 32px)`
- [x] 6.3 新增 `.reason-sub-table th, .reason-sub-table td`：`padding: 6px 10px; border-bottom: 1px solid var(--ya-border); text-align: left`
- [x] 6.4 移除 `.match-pill`、`.match-exact`、`.match-partial`、`.match-none` CSS rules（如有）

## 7. 驗證

- [ ] 7.1 手動驗證：選 2026/02 查詢後，點擊一筆有 MES 資料的告警列「查看原因」→ 展開明細
- [ ] 7.2 手動驗證：點擊另一列 → 前一列收合，新列展開
- [ ] 7.3 手動驗證：點擊同一列「收合」→ 正常收合
- [ ] 7.4 手動驗證：「映射狀態」欄位已不存在
- [ ] 7.5 確認 `GET /api/yield-alert/reason-detail?workorder=GA...&date_bucket=2026-02-15` 直接回傳正確 MES 資料
