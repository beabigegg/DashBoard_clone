# Change Request

## Original Request

（此為調查過程中發現、非本次追蹤範圍的獨立缺陷，先記錄封存供之後排入排程）

yield-alert-center 的「匯出全部 CSV」功能，在非 DuckDB-WASM 模式（`duckdbMode` 未啟用，走 `frontend/src/yield-alert-center/App.vue::exportAllAlertsCSV()` 的 server fallback 分支，約 699-724 行）呼叫 `GET /api/yield-alert/alerts` 時，`baseParams` 完全沒有帶 `start_date`/`end_date`（只有 `query_id`、篩選條件、分頁參數）。

但後端 `src/mes_dashboard/routes/yield_alert_routes.py::api_yield_alert_alerts()`（476-558 行）透過 `_parse_date_range(required=True)`（78-93 行）**強制要求** `start_date`/`end_date`，缺少時直接回 400 `VALIDATION_ERROR`「缺少必要參數: start_date, end_date」，且完全不讀取 `query_id`（該路由呼叫的是 `query_alert_candidates()`，`yield_alert_service.py` 裡一個獨立於 DuckDB spool 的舊查詢路徑，與 `/api/yield-alert/view` 用的 `_query_alerts()`（`yield_alert_sql_runtime.py`）是兩套不同實作）。

結果：只要使用者的查詢結果筆數低於 DuckDB-WASM 啟用門檻（`DUCKDB_THRESHOLD`），匯出 CSV 一定會直接失敗（顯示「匯出失敗，請稍後再試」），因為送出的請求必然缺少必要參數。目前之所以不常被使用者發現，是因為大部分查詢結果量體都會觸發 DuckDB-WASM 模式（`isDuckDBSupported()` 為 true 且 `total_row_count >= DUCKDB_THRESHOLD`），走的是 `duckdb.computeView()` 這條路，不會碰到這個壞掉的 server fallback。

## Business / User Goal

匯出 CSV 功能不應該因為查詢結果量體大小（是否觸發 DuckDB-WASM 模式）而出現「小資料集必定匯出失敗」的差異行為。

## Non-goals

- 不在此提案中一併修正 `yield-alert-kpi-csv-parity`（KPI 口徑統一 + CSV 浮點數格式化，已完成、獨立追蹤）已處理的問題。
- 不在此提案中評估是否要把 `query_alert_candidates()`（舊路徑）與 `_query_alerts()`（DuckDB spool 路徑）合併為單一實作——這可能是更大範圍的架構決策，需要另外評估。

## Constraints

（待後續 /cdd-new 分類與規劃時展開）

## Known Context

- 相關檔案：`frontend/src/yield-alert-center/App.vue`（`exportAllAlertsCSV`，約 674-733 行）、`src/mes_dashboard/routes/yield_alert_routes.py`（`api_yield_alert_alerts`、`_parse_date_range`）、`src/mes_dashboard/services/yield_alert_service.py`（`query_alert_candidates`）。
- 發現於 `yield-alert-kpi-csv-parity` 變更的調查階段，非該次變更的根因，故未併入其修正範圍。

## Open Questions

- 修法方向未定，至少有兩種候選：(a) 前端補送 `start_date`/`end_date`（用 `filters.start_date`/`filters.end_date`，兩者在 UI 上本來就必填）；或 (b) 讓 `GET /api/yield-alert/alerts` 改用 `query_id` 走 DuckDB spool（與 `/view` 用同一份查詢邏輯），一併解決這條路徑用的是舊版 `query_alert_candidates()`、與 `/view` 的 `_query_alerts()` 是兩套邏輯的架構分裂問題。需要 spec-architect 評估。

## Requested Delivery Date / Priority

未排定 — 封存為 backlog 候選項目。
