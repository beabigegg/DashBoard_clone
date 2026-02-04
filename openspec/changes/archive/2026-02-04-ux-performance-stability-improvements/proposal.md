## Why

目前系統在 SQL 查詢安全架構重構後，核心功能已穩定運作。然而，根據代碼審查發現以下改善空間：

1. **使用者體驗不一致**：錯誤訊息直接暴露技術細節（如 ORA-xxxxx）、API 回應格式不統一、批次查詢缺乏進度回饋
2. **穩定度風險**：缺乏熔斷機制，當 Oracle 異常時所有請求仍會嘗試連線導致雪崩；Redis 降級只有單層 fallback
3. **效能監控不足**：慢查詢僅記錄 warning，缺乏量化指標追蹤；部分歷史查詢仍有優化空間
4. **管理功能不足**：管理員缺乏效能監控視覺化介面；當 worker 異常時需 SSH 登入伺服器手動處理

## What Changes

### 使用者體驗 (UX)
- 新增統一的 API 回應格式與錯誤代碼系統
- 錯誤訊息分層：使用者友善訊息 vs 技術日誌

### 穩定度
- 新增 Circuit Breaker 熔斷機制，防止連鎖失敗
- 擴充健康檢查，新增深度檢查與延遲指標
- 新增本地 LRU 快取作為 Redis 的二級 fallback

### 效能
- 新增查詢效能指標收集（P50/P95/P99 延遲）

### 管理 (Admin)
- 新增效能報表頁面至 Admin，視覺化顯示系統效能指標
- 新增管理員 log 紀錄檢視（可篩選/搜尋）
- 評估並實作 Worker 重啟機制，允許管理員從前端觸發服務重啟

## Non-Goals (本次範圍外)

以下項目暫不納入本次變更，留待後續評估：

- **Excel 批次查詢進度回報**：需評估前後端架構變更幅度，可能需要 WebSocket 或 Server-Sent Events
- **歷史趨勢查詢優化（預計算/分層快取）**：需先有查詢效能指標數據，確認瓶頸後再規劃優化策略

## Capabilities

### New Capabilities

- `api-response-format`: 統一的 API 回應格式與錯誤代碼系統，提供一致的成功/失敗回應結構
- `circuit-breaker`: 資料庫連線熔斷機制，防止連鎖失敗與資源耗盡
- `query-metrics`: 查詢效能指標收集與監控，追蹤延遲分布與慢查詢統計
- `local-cache-fallback`: 本地 LRU 記憶體快取，作為 Redis 不可用時的二級 fallback
- `admin-performance-dashboard`: 管理員效能報表頁面，顯示系統健康狀態、效能指標、熔斷器狀態與近期 log 紀錄
- `admin-worker-control`: 管理員服務控制功能，提供 Worker 重啟機制（需評估安全性與可行性）

### Modified Capabilities

- `health-check`: 擴充深度檢查功能，新增延遲指標、快取新鮮度檢查、熔斷器狀態

## Impact

### 程式碼變更

**新增檔案：**
- `src/mes_dashboard/core/response.py` - API 回應格式與錯誤代碼
- `src/mes_dashboard/core/circuit_breaker.py` - 熔斷器實作
- `src/mes_dashboard/core/metrics.py` - 效能指標收集
- `src/mes_dashboard/core/local_cache.py` - 本地 LRU 快取
- `src/mes_dashboard/core/worker_control.py` - Worker 控制模組（評估後實作）
- `src/mes_dashboard/templates/admin/performance.html` - 效能報表頁面
- `src/mes_dashboard/core/log_store.py` - SQLite log 存取與查詢
- `scripts/worker_watchdog.py` - Worker 監控與重啟服務（可選，依架構決策）

**修改檔案：**
- `src/mes_dashboard/core/database.py` - 整合熔斷器
- `src/mes_dashboard/core/cache.py` - 整合本地快取 fallback
- `src/mes_dashboard/routes/health_routes.py` - 擴充健康檢查
- `src/mes_dashboard/routes/admin_routes.py` - 新增效能報表、log 檢視與服務控制路由
- `src/mes_dashboard/services/*.py` - 統一錯誤回應格式
- `src/mes_dashboard/routes/*.py` - 統一 API 回應格式

### API 影響

- 所有 API 回應格式將統一，但維持向下相容（現有欄位保留）
- 新增 `GET /health/deep` 深度健康檢查端點
- 新增 `GET /admin/api/metrics` 效能指標端點
- 新增 `GET /admin/performance` 效能報表頁面
- 新增 `GET /admin/api/logs` 近期 log 紀錄查詢 API
- 新增 `GET /admin/api/worker/status` Worker 狀態查詢 API
- 新增 `POST /admin/api/worker/restart` Worker 重啟 API（需評估）

### 依賴

- 無新增 Python 第三方依賴，使用 Python 標準函式庫實作（包含 `sqlite3`）
- 熔斷器：使用 `threading` + `time` 實作
- 本地快取：使用 `functools.lru_cache` 或自訂 TTL cache
- 指標收集：使用 `collections.deque` 實作滑動視窗
- 管理員 log 檢視：使用 SQLite 儲存（本機檔案）
- 前端圖表：使用 Chart.js（前端依賴）
- Worker 控制：評估方案（見下方）

### Worker 重啟機制評估

**方案選項：**

| 方案 | 說明 | 優點 | 缺點 |
|------|------|------|------|
| A. Gunicorn SIGHUP | 透過信號觸發 graceful reload | 簡單、原生支援 | Flask 無法直接發送信號給父進程 |
| B. Supervisor/Systemd | 透過 subprocess 呼叫 systemctl | 標準做法 | 需要 sudo 權限配置 |
| C. 控制檔案 + Watchdog | 寫入標記檔案，外部腳本監控並重啟 | 安全、解耦 | 需要額外的監控腳本 |
| D. 獨立控制服務 | 建立輕量 HTTP 服務專門處理重啟 | 完全隔離 | 架構複雜度增加 |

**建議：** 在 Design 階段評估各方案的安全性與可行性，選擇最適合的實作方式。

### 安全考量

- Worker 重啟 API 必須限制僅管理員可存取
- 應有操作日誌記錄（誰、何時、從哪個 IP 觸發）
- 考慮加入確認機制或冷卻時間，防止誤操作
- 評估是否需要二次驗證（如重新輸入密碼）

### 測試

- `tests/test_api_response.py` - API 回應格式測試
- `tests/test_circuit_breaker.py` - 熔斷器狀態轉換測試
- `tests/test_query_metrics.py` - 指標收集測試
- `tests/test_local_cache.py` - 本地快取測試
- `tests/test_admin_performance.py` - 效能報表 API 測試
- `tests/test_admin_logs.py` - 管理員 log 檢視 API 測試
- `tests/test_worker_control.py` - Worker 控制測試（模擬）
