# Change Request

## Original Request

修正 yield-alert-center（良率警報中心）的 KPI 卡片與明細匯出口徑不一致問題，並修正 CSV 匯出的浮點數精度 bug。

背景（已完成調查，見下方根因）：

1. 口徑不一致：
   - KPI 卡片「移轉量」「報廢量」來自 `GET /api/yield-alert/view` → `_query_summary()`（`src/mes_dashboard/services/yield_alert_sql_runtime.py:196-240`），對「日期範圍 + 部門/製程篩選」範圍內全部資料 `SUM(TRANSACTION_QTY)`/`SUM(SCRAP_QTY)`，不套用 `risk_threshold`、`min_scrap_qty`，也不限制 `SCRAP_QTY <> 0`，且只用 `dept_proc_where`（不含 lines/packages/types/functions 篩選）。
   - 明細清單與其 CSV 匯出來自 `_query_alerts()`（同檔案 491-670 行），只挑出「告警候選」：`WHERE SCRAP_QTY <> 0 AND NOT (yield_pct >= risk_threshold AND scrap_qty < min_scrap_qty)`，且套用全部 6 個維度篩選（含 lines/packages/types/functions）。
   - 兩者口徑天差地遠，使用者把 CSV 明細加總跟 KPI 卡片對不起來。
   - 期望方向：讓 KPI 卡片的「移轉量」「報廢量」改為反映「目前篩選條件下的告警候選」總量（即與清單/CSV 匯出口徑一致），而不是全廠總量。也就是 KPI 卡片應該套用跟 `_query_alerts()` 相同的 `risk_threshold`、`min_scrap_qty`、`SCRAP_QTY<>0`、以及完整的 6 維度篩選條件。
   - 已知技術陷阱：`_query_alerts()` 的 `alerts_filtered` 是以 `(DATE_BUCKET, WORKORDER, REASON_CODE, REASON_NAME, DEPARTMENT_GROUP, PROCESS_CATEGORY, LINE_NAME, PACKAGE_NAME, TYPE_NAME, FUNCTION_NAME, OPERATION_TEXT)` 分組（含 REASON_CODE），但 `transaction_qty` 是用不含 REASON_CODE 的較粗維度（`tx_lookup`，見 533-548 行）join 進來的。如果同一個 (workorder+date+dept+...) 群組同時有多個不同 reason_code 造成報廢，直接對 `alerts_filtered` 的 `transaction_qty` 做 SUM 會重複計算同一批的移轉量。`scrap_qty` 因為本來就是照 reason_code 分組加總，不會重複計算。統一口徑時務必先用 tx dedup 維度（不含 REASON_CODE）去重 `transaction_qty` 後再加總，避免虛增移轉量。
   - 這個口徑定義目前沒有寫在 `contracts/business/business-rules.md` 的 YA-01~YA-12 規則裡，需要新增規則明確記載。

2. CSV 浮點數精度 bug：
   - 前端 `frontend/src/yield-alert-center/App.vue` 的 `_buildAlertsCSV()`（643-660 行）在組 CSV 欄位時，對 `toPcs(r.transaction_qty)`、`toPcs(r.scrap_qty)`（653-654 行）沒有做任何四捨五入或格式化，直接用 `String(v)` 轉字串寫進 CSV。同一函式裡 `yield_pct`、`risk_score` 卻都有 `.toFixed(4)`/`.toFixed(2)`（655、657 行）。
   - 根因鏈：Oracle 的 K-PCS 數值理論上是 0.001 的整數倍，但 DuckDB 多層 CTE 對 DOUBLE 做 SUM/ROUND（`yield_alert_sql_runtime.py:656-657` 的 `ROUND(CAST(transaction_qty AS DOUBLE), 4)`）後仍會殘留二進位浮點誤差（例如 4.012 變成 4.0119999999999996）；前端 `toPcs()`（`frontend/src/yield-alert-center/utils.ts:6-8`）把這個值 `*1000` 換算成 pcs 時誤差被放大成類似 `4011.9999999999995` 這種醜陋數字，直接寫進 CSV。畫面上的表格（`App.vue:1159-1160`）因為用了 `toPcs(...).toLocaleString()` 而被自動四捨五入掩蓋掉，只有 CSV 沒有這層保護。
   - 使用者實測發現這類長位數、又被雙引號包住的字串在 Excel 開啟時常被誤判為「以文字方式儲存的數字」，導致 `SUM()` 直接跳過該儲存格，這正是使用者回報「CSV 加總對不上」的部分原因（另一部分原因是上述口徑不一致）。
   - 修法：CSV 匯出時對 `transaction_qty`/`scrap_qty` 也要做適當的四捨五入/格式化（例如比照 `yield_pct`/`risk_score` 的 `.toFixed()` 處理，或使用符合 pcs 顆粒度的精度），避免把原始浮點誤差寫進輸出檔案。

觀察到的可驗收成功標準：
- KPI 卡片「移轉量」「報廢量」與同一組篩選條件下匯出的 CSV 明細加總（經 tx dedup 後）在數值上一致（容許合理的四捨五入誤差，例如 pcs 級精度）。
- CSV 匯出檔案中 transaction_qty/scrap_qty 欄位不再出現超過小數點後 2-3 位的浮點雜訊（例如 `4011.9999999999995` 這類值），改為乾淨的四捨五入數字。

## Business / User Goal

## Non-goals

## Constraints

## Known Context

## Open Questions

## Requested Delivery Date / Priority
