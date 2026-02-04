## ADDED Requirements

### Requirement: 效能報表頁面

系統 SHALL 提供管理員效能報表頁面。

#### Scenario: 存取效能報表頁面
- **WHEN** 管理員存取 `GET /admin/performance`
- **THEN** 系統 SHALL 顯示效能報表頁面
- **AND** HTTP 狀態碼 SHALL 為 200

#### Scenario: 非管理員禁止存取
- **WHEN** 非管理員存取 `GET /admin/performance`
- **THEN** 系統 SHALL 重導向至登入頁面
- **OR** HTTP 狀態碼 SHALL 為 403

---

### Requirement: 系統狀態顯示

效能報表頁面 SHALL 顯示系統各元件的健康狀態。

#### Scenario: 顯示資料庫狀態
- **WHEN** 載入效能報表頁面
- **THEN** 頁面 SHALL 顯示資料庫連線狀態
- **AND** 狀態 SHALL 為 ✅ (正常) 或 ❌ (異常)

#### Scenario: 顯示 Redis 狀態
- **WHEN** 載入效能報表頁面
- **THEN** 頁面 SHALL 顯示 Redis 連線狀態
- **AND** 若 Redis 停用則顯示「已停用」

#### Scenario: 顯示熔斷器狀態
- **WHEN** 載入效能報表頁面
- **THEN** 頁面 SHALL 顯示熔斷器狀態
- **AND** 狀態 SHALL 為 CLOSED、OPEN 或 HALF_OPEN

#### Scenario: 顯示 Worker 數量
- **WHEN** 載入效能報表頁面
- **THEN** 頁面 SHALL 顯示目前回應的 Worker PID

---

### Requirement: 效能指標顯示

效能報表頁面 SHALL 顯示查詢效能指標。

#### Scenario: 顯示延遲百分位數
- **WHEN** 載入效能報表頁面
- **THEN** 頁面 SHALL 顯示 P50、P95、P99 延遲值
- **AND** 單位 SHALL 為毫秒或秒

#### Scenario: 顯示慢查詢統計
- **WHEN** 載入效能報表頁面
- **THEN** 頁面 SHALL 顯示慢查詢數量
- **AND** SHALL 顯示慢查詢比例

#### Scenario: 延遲分布視覺化
- **WHEN** 載入效能報表頁面
- **THEN** 頁面 SHALL 顯示延遲分布圖表
- **AND** 圖表 SHALL 使用 Chart.js 或類似工具

---

### Requirement: 快取狀態顯示

效能報表頁面 SHALL 顯示快取運作狀態。

#### Scenario: 顯示 Redis 快取命中率
- **WHEN** 載入效能報表頁面
- **THEN** 頁面 SHALL 顯示 Redis 快取命中率

#### Scenario: 顯示本地快取命中率
- **WHEN** 載入效能報表頁面
- **THEN** 頁面 SHALL 顯示本地快取命中率

#### Scenario: 顯示快取最後更新時間
- **WHEN** 載入效能報表頁面
- **THEN** 頁面 SHALL 顯示快取最後更新時間

---

### Requirement: 自動重新整理

效能報表頁面 SHALL 支援自動重新整理。

#### Scenario: 手動重新整理
- **WHEN** 點擊「重新整理」按鈕
- **THEN** 頁面 SHALL 重新載入所有指標資料
- **AND** SHALL NOT 整頁重新載入（使用 AJAX）

#### Scenario: 自動重新整理間隔
- **WHEN** 啟用自動重新整理
- **THEN** 頁面 SHALL 每 30 秒自動更新指標
- **AND** 使用者 SHALL 可以停用自動重新整理

---

### Requirement: 系統狀態 API

系統 SHALL 提供 API 取得系統狀態資訊。

#### Scenario: 取得系統狀態
- **WHEN** 呼叫 `GET /admin/api/system-status`
- **AND** 使用者為管理員
- **THEN** 回應 SHALL 包含：
  - `database`: 資料庫狀態
  - `redis`: Redis 狀態
  - `circuit_breaker`: 熔斷器狀態
  - `cache`: 快取狀態
  - `worker_pid`: 當前 Worker PID

---

### Requirement: Log 紀錄檢視

效能報表頁面 SHALL 顯示近期 log 紀錄。

#### Scenario: 顯示近期 log
- **WHEN** 管理員載入效能報表頁面
- **THEN** 頁面 SHALL 顯示最近 N 筆 log（預設 200 筆）
- **AND** 每筆 log SHALL 顯示時間、等級、來源、訊息

#### Scenario: 篩選與搜尋
- **WHEN** 管理員選擇等級（INFO/WARNING/ERROR）或輸入關鍵字
- **THEN** 頁面 SHALL 即時更新顯示結果

---

### Requirement: Log API

系統 SHALL 提供 API 取得近期 log 紀錄。

#### Scenario: 取得 log 紀錄
- **WHEN** 呼叫 `GET /admin/api/logs`
- **AND** 使用者為管理員
- **THEN** 回應 SHALL 包含 log 清單
- **AND** HTTP 狀態碼 SHALL 為 200

#### Scenario: Log API 查詢參數
- **WHEN** 呼叫 `GET /admin/api/logs` 並帶入查詢參數
- **THEN** API SHALL 支援：
  - `level`：等級過濾（INFO/WARNING/ERROR）
  - `q`：關鍵字搜尋
  - `limit`：回傳筆數（預設 200）
  - `since`：起始時間（ISO-8601）

#### Scenario: 非管理員禁止存取
- **WHEN** 非管理員呼叫 `GET /admin/api/logs`
- **THEN** HTTP 狀態碼 SHALL 為 403
---

### Requirement: Log 資料儲存

系統 SHALL 將 log 寫入本機 SQLite 供管理員查詢。

#### Scenario: 寫入 SQLite log store
- **WHEN** 系統產生 log 紀錄
- **THEN** log SHALL 寫入本機 SQLite log store
- **AND** 供 `GET /admin/api/logs` 查詢
