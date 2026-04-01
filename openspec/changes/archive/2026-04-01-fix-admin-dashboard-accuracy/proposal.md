## Why

Admin Dashboard 有資訊正確性與外觀一致性問題，會讓維運人員誤判系統狀態，且視覺上與其他頁面脫節：

**問題 1：RQ Worker 運行時間虛增 8 小時**

RQ 的 `Worker.birth_date` 使用 `datetime.utcnow()` 產生 naive datetime（無時區標記），後端透過 `.isoformat()` 序列化輸出如 `"2026-04-01T00:00:00"`。前端 `new Date()` 解析不帶時區標記的 ISO 字串時，依 JS 規範視為本地時間（UTC+8），導致 `Date.now() - new Date(birthDate)` 差值多出 8 小時。同頁的 `worker_start_time` 則用 `datetime.fromtimestamp()`（本地時間），兩者混用不同時區基準。

**問題 2：Pareto 物化層面板永遠全 0**

CacheTab 的「Pareto 物化層」區塊顯示命中率、建構次數等全部為 0。原因是 `PARETO_MATERIALIZATION_ENABLED` 和 `PARETO_MATERIALIZATION_READ_ENABLED` 兩個 flag 從未開啟（預設 false，.env 也是 false）。實際的 Pareto 計算已由 `reject_cache_sql_runtime`（DuckDB over spool parquet）接管，物化層是被取代的中間產物，面板在監控一個從未啟用的功能。

**問題 3：Admin 頁面外觀與全站設計脫節**

Admin Dashboard 和 Admin Performance 各自手寫 header、container 樣式，與一般業務頁面（resource-history、reject-history 等）使用的共用 `PageHeader` 元件和 `header-gradient` 樣式不一致：

| 比較項目 | 業務頁面 | Admin Dashboard | Admin Performance |
|----------|----------|-----------------|-------------------|
| Header | 共用 `PageHeader` 元件 + `header-gradient` class | 自訂 `.dashboard-header`（底部圓角、負 margin 出血） | 自訂 `.perf-header`（同出血模式） |
| 容器寬度 | `max-width: 1800px`（`.dashboard` class） | `max-width: 1280px` | `max-width: 1280px` |
| 標題樣式 | `font-size: 24px`、`letter-spacing: 0.2px` | `font-size: 1.4rem`、`font-weight: 700` | 同 admin-dashboard |
| Header 圓角 | `border-radius: 12px`（四角） | `border-radius: 0 0 12px 12px`（僅底部） | 同 admin-dashboard |

Admin 頁面以窄版出血式 header 呈現，與業務頁面的圓角卡片式 header 視覺語言不同。

## What Changes

### RQ Worker 時區修正
- 後端 `rq_monitor_service.py` 的 `get_rq_worker_details()` 在序列化 `w.birth_date` 時，補上 UTC 時區標記（`replace(tzinfo=timezone.utc)`），使輸出帶 `+00:00` 後綴。
- 後端 `admin_routes.py` 的 `api_worker_status()` 在序列化 `worker_start_time` 時，同樣使用 timezone-aware datetime，確保 Admin API 時間欄位語義一致。

### Pareto 物化層面板移除
- 前端 `CacheTab.vue` 移除 Pareto 物化層的整個 SectionCard（命中率、建構次數等）及相關 computed properties。
- 後端 `admin_routes.py` 的 `api_performance_detail()` 移除 `pareto_materialization` 欄位的收集。
- 不刪除 `reject_pareto_materialized.py` 本身 — 它仍在 runtime fallback chain 中被呼叫（只是永遠 return None），移除模組需要更大範圍的重構，不在本次範圍內。

### Admin 頁面外觀標準化
- Admin Dashboard (`App.vue`) 的 header 改用共用 `PageHeader` 元件，tab 列保留在 header 下方。移除 `style.css` 中自訂的 `.dashboard-header` 出血式樣式，改走 `header-gradient` 四角圓角卡片模式。
- Admin Performance (`App.vue`) 的 header 同樣改用 `PageHeader`，移除 `.perf-header` 出血式樣式。
- 容器 `max-width` 從 `1280px` 調為 `1800px`，與業務頁面的 `.dashboard` class 對齊。
- 標題 `font-size` 統一為 `24px`，與 `header-gradient h1` 一致。
- Admin Dashboard 和 Admin Performance 的 `style.css` 中移除冗餘的 header 相關 CSS（由共用樣式接管）。

## Capabilities

### Changed Capabilities
- `admin-dashboard-worker-tab`: RQ Worker 運行時間與啟動時間的時區處理修正。
- `admin-dashboard-cache-tab`: 移除無效的 Pareto 物化層監控面板。
- `admin-dashboard-layout`: Header 改用共用 PageHeader 元件，容器寬度與標題樣式對齊全站設計。
- `admin-performance-layout`: Header 改用共用 PageHeader 元件，容器寬度與標題樣式對齊全站設計。

## Scope

- `src/mes_dashboard/services/rq_monitor_service.py` — `birth_date` 序列化加 UTC 標記
- `src/mes_dashboard/routes/admin_routes.py` — `worker_start_time` 改 timezone-aware；移除 `pareto_materialization` telemetry 收集
- `frontend/src/admin-dashboard/App.vue` — header 改用 PageHeader 元件
- `frontend/src/admin-dashboard/style.css` — 移除自訂 header CSS，調整容器寬度
- `frontend/src/admin-dashboard/tabs/CacheTab.vue` — 移除 Pareto 物化層面板
- `frontend/src/admin-performance/App.vue` — header 改用 PageHeader 元件
- `frontend/src/admin-performance/style.css` — 移除自訂 header CSS，調整容器寬度
- `tests/test_rq_monitor_service.py` — 驗證 `birth_date` 輸出帶 `+00:00`

## Non-goals

- 不重構整個專案的時區處理策略。
- 不刪除 `reject_pareto_materialized.py` 模組（仍在 fallback chain 中）。
- 不替換為 DuckDB cache-sql telemetry 面板（目前 cache-sql 無聚合 telemetry API，需另開 change）。
- 不修改前端 `formatUptime()` 邏輯。
- 不改動 admin 頁面 tab 互動邏輯和內容區佈局（僅標準化 header 和容器）。
