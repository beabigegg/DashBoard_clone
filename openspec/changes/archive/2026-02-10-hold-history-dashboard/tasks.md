## 1. SQL 檔案建立

- [x] 1.1 建立 `src/mes_dashboard/sql/hold_history/` 目錄
- [x] 1.2 建立 `trend.sql` — calendar-spine cross-join 每日聚合查詢（翻譯 hold_history.md 邏輯，含 07:30 班別邊界、同日去重、Future Hold 去重、品質分類）
- [x] 1.3 建立 `reason_pareto.sql` — GROUP BY HOLDREASONNAME，含 count/qty/pct/cumPct 計算
- [x] 1.4 建立 `duration.sql` — 已 release hold 的時長分布（4 bucket: <4h, 4-24h, 1-3d, >3d）
- [x] 1.5 建立 `department.sql` — GROUP BY HOLDEMPDEPTNAME / HOLDEMP，含 hold/release 計數及平均時長
- [x] 1.6 建立 `list.sql` — paginated 明細查詢（含 HOLDCOMMENTS/RELEASECOMMENTS，未 release 用 SYSDATE 計算時長）

## 2. 後端服務層

- [x] 2.1 建立 `src/mes_dashboard/services/hold_history_service.py`，實作 SQL 載入輔助函式（從 sql/hold_history/ 讀取 .sql 檔案）
- [x] 2.2 實作 `get_hold_history_trend(start_date, end_date)` — 執行 trend.sql，回傳三種 hold_type 的每日聚合資料
- [x] 2.3 實作 trend Redis 快取邏輯 — 近二月快取（key: `hold_history:daily:{YYYY-MM}`，TTL 12hr），跨月查詢拼接，超過二月直接 Oracle
- [x] 2.4 實作 `get_hold_history_reason_pareto(start_date, end_date, hold_type)` — 執行 reason_pareto.sql
- [x] 2.5 實作 `get_hold_history_duration(start_date, end_date, hold_type)` — 執行 duration.sql
- [x] 2.6 實作 `get_hold_history_department(start_date, end_date, hold_type, reason=None)` — 執行 department.sql，回傳部門層級含 persons 陣列
- [x] 2.7 實作 `get_hold_history_list(start_date, end_date, hold_type, reason=None, page=1, per_page=50)` — 執行 list.sql，回傳 paginated 結果

## 3. 後端路由層

- [x] 3.1 建立 `src/mes_dashboard/routes/hold_history_routes.py` Flask Blueprint
- [x] 3.2 實作 `GET /hold-history` 頁面路由 — send_from_directory / fallback HTML
- [x] 3.3 實作 `GET /api/hold-history/trend` — 呼叫 service，rate limit 60/60s
- [x] 3.4 實作 `GET /api/hold-history/reason-pareto` — 呼叫 service
- [x] 3.5 實作 `GET /api/hold-history/duration` — 呼叫 service
- [x] 3.6 實作 `GET /api/hold-history/department` — 呼叫 service，含 optional reason 參數
- [x] 3.7 實作 `GET /api/hold-history/list` — 呼叫 service，rate limit 90/60s，含 optional reason 參數
- [x] 3.8 在 `routes/__init__.py` 註冊 hold_history_bp Blueprint

## 4. 頁面註冊與 Vite 配置

- [x] 4.1 在 `data/page_status.json` 新增 `/hold-history` 頁面（status: dev, drawer: reports）
- [x] 4.2 在 `frontend/vite.config.js` 新增 `'hold-history': resolve(__dirname, 'src/hold-history/index.html')` entry point

## 5. 前端頁面骨架

- [x] 5.1 建立 `frontend/src/hold-history/` 目錄結構（index.html, main.js, App.vue, style.css）
- [x] 5.2 實作 `App.vue` — 頁面主容器、狀態管理（filterBar, reasonFilter, pagination）、API 呼叫流程、cascade filter 邏輯
- [x] 5.3 實作 `FilterBar.vue` — DatePicker（預設當月）+ Hold Type radio（品質異常/非品質異常/全部）

## 6. 前端元件 — KPI 與趨勢圖

- [x] 6.1 實作 `SummaryCards.vue` — 6 張 KPI 卡片（Release, New Hold, Future Hold, 淨變動, 期末 On Hold, 平均時長），Release 綠色正向、New/Future 紅/橙負向
- [x] 6.2 實作 `DailyTrend.vue` — ECharts 折線+柱狀混合圖，左 Y 軸增減量（Release↑綠, New↓紅, Future↓橙 stacked），右 Y 軸 On Hold 折線

## 7. 前端元件 — 分析圖表

- [x] 7.1 實作 `ReasonPareto.vue` — ECharts Pareto 圖（柱狀 count + 累積%折線），可點擊觸發 reasonFilter toggle
- [x] 7.2 實作 `DurationChart.vue` — ECharts 橫向柱狀圖（<4h, 4-24h, 1-3天, >3天），顯示 count 和百分比

## 8. 前端元件 — 表格

- [x] 8.1 實作 `FilterIndicator.vue` — 顯示 active reason filter 及清除按鈕
- [x] 8.2 實作 `DepartmentTable.vue` — 部門統計表，可展開看個人層級，受 reasonFilter 篩選
- [x] 8.3 實作 `DetailTable.vue` — paginated 明細表（12 欄位），未 release 顯示 "仍在 Hold"，受 reasonFilter 篩選

## 9. 後端測試

- [x] 9.1 建立 `tests/test_hold_history_routes.py` — 測試頁面路由（含 admin session）、5 支 API endpoint 參數傳遞、rate limiting、error handling
- [x] 9.2 建立 `tests/test_hold_history_service.py` — 測試 trend 快取邏輯（cache hit/miss/cross-month）、各 service function 的 Oracle 查詢與回傳格式、hold_type 分類、shift boundary 邏輯

## 10. 整合驗證

- [x] 10.1 執行既有測試確認無回歸（test_hold_overview_routes, test_wip_service, test_page_registry）
- [x] 10.2 驗證 vite build 成功產出 hold-history.html/js/css 且不影響既有 entry points
