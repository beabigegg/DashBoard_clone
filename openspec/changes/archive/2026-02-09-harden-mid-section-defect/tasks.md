## 1. P0 — 分散式鎖防止重複管線執行

- [x] 1.1 在 `mid_section_defect_service.py` 的 `query_analysis()` cache miss 後加入 `try_acquire_lock` / `release_lock` 包裹計算區段
- [x] 1.2 實作 lock-or-wait 邏輯：未取得鎖時輪詢 `cache_get()` 每 0.5s，最多 90s，超時 fail-open
- [x] 1.3 在 `finally` 區塊確保鎖釋放，取得鎖後再做 double-check cache

## 2. P1a — 高成本路由限速

- [x] 2.1 在 `mid_section_defect_routes.py` import `configured_rate_limit` 並建立 3 個限速器（analysis 6/60s、detail 15/60s、export 3/60s）
- [x] 2.2 將限速 decorator 套用到 `/analysis`、`/analysis/detail`、`/export` 三個路由

## 3. P1b + P2a — 前端篩選分離與請求取消

- [x] 3.1 在 `App.vue` 新增 `committedFilters` ref，`handleQuery()` 時從 `filters` 快照
- [x] 3.2 修改 `buildFilterParams()` 和 `exportCsv()` 讀取 `committedFilters` 而非 `filters`
- [x] 3.3 `initPage()` 設定預設日期後同步快照到 `committedFilters`
- [x] 3.4 從 `useAutoRefresh` 解構 `createAbortSignal`，在 `loadAnalysis()` 加入 `'msd-analysis'` signal
- [x] 3.5 `loadDetail()` 接受外部 signal 參數，獨立翻頁時使用 `'msd-detail'` key
- [x] 3.6 `loadAnalysis()` 和 `loadDetail()` catch 區塊靜默處理 `AbortError`

## 4. P2b — 上游歷史 SQL 端分類

- [x] 4.1 修改 `upstream_history.sql` CTE 加入 `CASE WHEN` 將 `WORKCENTERNAME` 分類為 `WORKCENTER_GROUP`（12 組 + NULL fallback）
- [x] 4.2 確保 CASE 順序正確（`元件切割`/`PKG_SAW` 在 `切割` 之前）
- [x] 4.3 修改 `_fetch_upstream_history()` 讀取 SQL 回傳的 `WORKCENTER_GROUP` 欄位，移除 `get_workcenter_group()` 逐行呼叫與 order 4-11 過濾

## 5. P3 — 測試覆蓋

- [x] 5.1 建立 `tests/test_mid_section_defect_routes.py`：success、400 參數驗證、500 service 失敗、429 rate limit（共 9 個測試）
- [x] 5.2 建立 `tests/test_mid_section_defect_service.py`：日期驗證、分頁邏輯、loss reasons 快取（共 9 個測試）

## 6. 驗證

- [x] 6.1 `npm run build` 前端建置通過
- [x] 6.2 `pytest tests/test_mid_section_defect_routes.py tests/test_mid_section_defect_service.py -v` 全部通過
