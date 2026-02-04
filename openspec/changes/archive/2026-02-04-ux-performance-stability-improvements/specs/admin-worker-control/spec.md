## ADDED Requirements

### Requirement: Worker 重啟觸發

系統 SHALL 允許管理員從前端觸發 Worker 重啟。

#### Scenario: 觸發重啟請求
- **WHEN** 管理員呼叫 `POST /admin/api/worker/restart`
- **AND** 使用者為管理員
- **THEN** 系統 SHALL 寫入重啟標記檔案
- **AND** HTTP 狀態碼 SHALL 為 202 (Accepted)
- **AND** 回應 SHALL 包含 `"message": "重啟請求已提交"`

#### Scenario: 非管理員禁止操作
- **WHEN** 非管理員呼叫 `POST /admin/api/worker/restart`
- **THEN** HTTP 狀態碼 SHALL 為 403
- **AND** 操作 SHALL NOT 執行

---

### Requirement: 重啟冷卻時間

系統 SHALL 實作重啟冷卻機制，防止頻繁重啟。

#### Scenario: 冷卻時間內拒絕
- **WHEN** 管理員呼叫 `POST /admin/api/worker/restart`
- **AND** 距離上次重啟不足 60 秒
- **THEN** HTTP 狀態碼 SHALL 為 429 (Too Many Requests)
- **AND** 回應 SHALL 包含剩餘冷卻秒數

#### Scenario: 冷卻時間後允許
- **WHEN** 管理員呼叫 `POST /admin/api/worker/restart`
- **AND** 距離上次重啟已超過 60 秒
- **THEN** 重啟請求 SHALL 被接受

#### Scenario: 查詢冷卻狀態
- **WHEN** 呼叫 `GET /admin/api/worker/status`
- **THEN** 回應 SHALL 包含：
  - `cooldown_remaining`: 剩餘冷卻秒數（0 表示可用）
  - `last_restart`: 上次重啟時間
  - `last_restart_by`: 上次重啟操作者

---

### Requirement: 重啟操作日誌

系統 SHALL 記錄所有重啟操作。

#### Scenario: 記錄操作資訊
- **WHEN** 管理員觸發重啟
- **THEN** 系統 SHALL 記錄：
  - 操作者（email/username）
  - 操作時間
  - 來源 IP 位址
  - 操作結果

#### Scenario: 日誌儲存位置
- **WHEN** 記錄重啟操作
- **THEN** 日誌 SHALL 寫入系統日誌（INFO 級別）
- **AND** SHALL 寫入獨立的操作日誌檔案

---

### Requirement: 前端確認機制

效能報表頁面 SHALL 實作重啟確認機制。

#### Scenario: 顯示確認對話框
- **WHEN** 管理員點擊「重啟 Workers」按鈕
- **THEN** 系統 SHALL 顯示確認對話框
- **AND** 對話框 SHALL 警告此操作會短暫影響服務

#### Scenario: 確認後執行
- **WHEN** 管理員在確認對話框點擊「確定」
- **THEN** 系統 SHALL 發送重啟請求

#### Scenario: 取消操作
- **WHEN** 管理員在確認對話框點擊「取消」
- **THEN** 系統 SHALL NOT 發送重啟請求

---

### Requirement: Watchdog 腳本

系統 SHALL 提供 Watchdog 腳本監控重啟標記檔案。

#### Scenario: 監控標記檔案
- **WHEN** Watchdog 腳本運行中
- **THEN** 腳本 SHALL 每 5 秒檢查 `/tmp/mes_dashboard_restart.flag`

#### Scenario: 偵測到標記檔案
- **WHEN** Watchdog 偵測到標記檔案存在
- **THEN** 腳本 SHALL 發送 SIGHUP 信號給 Gunicorn master
- **AND** SHALL 刪除標記檔案
- **AND** SHALL 記錄重啟事件到日誌

#### Scenario: Gunicorn Graceful Reload
- **WHEN** Gunicorn master 收到 SIGHUP
- **THEN** Gunicorn SHALL 執行 graceful reload
- **AND** 現有請求 SHALL 完成後才終止 worker
- **AND** 新 worker SHALL 啟動接手

---

### Requirement: 重啟狀態回報

系統 SHALL 提供方式確認重啟是否完成。

#### Scenario: 查詢 Worker 啟動時間
- **WHEN** 呼叫 `GET /admin/api/worker/status`
- **THEN** 回應 SHALL 包含當前 worker 的啟動時間

#### Scenario: 前端顯示重啟結果
- **WHEN** 重啟請求已提交
- **THEN** 前端 SHALL 輪詢 worker 狀態
- **AND** SHALL 顯示「重啟中...」直到偵測到新 worker
