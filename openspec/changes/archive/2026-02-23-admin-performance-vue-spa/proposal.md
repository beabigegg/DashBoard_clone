## Why

現有 `/admin/performance` 是唯一仍使用 Jinja2 + vanilla JS + Chart.js 的頁面，與所有已遷移至 Vue 3 SPA 的報表頁面架構不一致。同時，隨著報表系統功能擴充（L1/L2 快取層、連線池、直連 Oracle 等），後端已具備豐富的遙測數據，但管理後台的監控面板覆蓋不足——缺少 Redis 詳情、ProcessLevelCache 統計、連線池飽和度、直連 Oracle 追蹤等關鍵資訊。

## What Changes

- 將 `/admin/performance` 從 Jinja2 server-rendered 頁面重建為 Vue 3 SPA（ECharts 取代 Chart.js）
- 新增 `GET /admin/api/performance-detail` API，整合 Redis INFO/SCAN、ProcessLevelCache registry、連線池狀態、直連計數等完整監控數據
- 後端 `ProcessLevelCache` 加入 `stats()` 方法與全域 registry，支援動態收集所有快取實例狀態
- 後端 `database.py` 加入直連 Oracle 計數器，追蹤非連線池的直接連線使用量
- 前端新增 GaugeBar / StatCard / StatusDot 可複用組件，提供 gauge 飽和度視覺化
- portal-shell 路由從 `renderMode: 'external'` 切換為 `'native'`
- Vite 構建新增 `admin-performance` entry point

## Capabilities

### New Capabilities
- `admin-performance-spa`: Vue 3 SPA 重建管理效能儀表板，包含 status cards、query performance、Redis 快取、記憶體快取、連線池、worker 控制、系統日誌等完整面板
- `cache-telemetry-api`: ProcessLevelCache stats() + 全域 registry + performance-detail API，提供所有記憶體快取、Redis 快取、route cache 的遙測數據
- `connection-pool-monitoring`: 連線池飽和度追蹤 + 直連 Oracle 計數器，完整呈現資料庫連線使用狀況
- `metrics-history-trending`: SQLite 持久化背景採集 + 時間序列趨勢圖，可回溯連線池飽和度、查詢延遲、Redis 記憶體、快取命中率等歷史數據

### Modified Capabilities
<!-- No existing spec-level requirements are changing -->

## Impact

- **Backend** (7 files): `core/cache.py`、`core/database.py`、`core/metrics_history.py`(NEW)、`routes/admin_routes.py`、`services/resource_cache.py`、`services/realtime_equipment_cache.py`、`services/reject_dataset_cache.py`、`app.py`
- **Frontend** (8 new + 3 modified): 新建 `admin-performance/` 目錄（index.html、main.js、App.vue、style.css、4 個組件含 TrendChart），修改 `vite.config.js`、`package.json`、`routeContracts.js`
- **API**: 新增 2 個 endpoint (`/admin/api/performance-detail`、`/admin/api/performance-history`)，既有 5 個 endpoint 不變
- **Rollback**: 舊 Jinja2 模板保留，可透過 `routeContracts.js` 切回 `renderMode: 'external'`
