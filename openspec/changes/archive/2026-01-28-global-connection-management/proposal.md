## Why

MES Dashboard 多次遇到 Worker Timeout 和前端請求失敗問題。目前的修復屬於「打補丁」形式，各頁面獨立實作錯誤處理，導致：

1. **不一致**：WIP 頁面有 `fetchWithTimeout` + `AbortController`，Tables 頁面沒有
2. **脆弱**：新功能容易忘記加入連線保護
3. **難維護**：錯誤處理邏輯分散在多個 HTML 檔案中

需要建立全局連線管理機制，讓所有頁面強制使用統一的 API Client，避免類似問題再次發生。

## What Changes

### 前端模組化
- 建立 `static/js/` 目錄，將共用 JavaScript 模組化
- 建立 `mes-api.js`：統一的 API Client，內建 timeout、retry、取消機制
- 建立 `toast.js`：統一的通知系統，顯示重試狀態與錯誤訊息
- 建立 `_base.html`：Base template，強制所有頁面載入核心模組

### 錯誤處理標準化
- 所有 API 請求必須透過 `MesApi.get()` / `MesApi.post()`
- 內建 Exponential Backoff Retry（1s → 2s → 4s，共 3 次）
- 自動顯示重試狀態（Toast 通知）
- 重試失敗後顯示手動重試按鈕
- 所有請求事件記錄到 console（含 request ID）

### 頁面遷移
- 所有現有頁面改用 `{% extends "_base.html" %}`
- 移除各頁面內嵌的 `fetchWithTimeout` 實作
- 統一使用 `MesApi` 進行 API 呼叫

## Capabilities

### New Capabilities

- `mes-api-client`: 統一的前端 API Client 模組，提供 timeout、retry、cancellation、deduplication 功能
- `toast-notification`: 前端通知系統，顯示 info/success/warning/error/loading 狀態
- `base-template`: Flask Jinja2 base template，強制載入核心 JS 模組

### Modified Capabilities

- `wip-detail`: 遷移至使用 MesApi，移除內嵌 fetchWithTimeout
- `wip-overview`: 遷移至使用 MesApi，移除內嵌 fetchWithTimeout
- `tables-page`: 加入錯誤處理，使用 MesApi

## Impact

- **新增檔案**:
  - `src/mes_dashboard/static/js/mes-api.js`
  - `src/mes_dashboard/static/js/toast.js`
  - `src/mes_dashboard/templates/_base.html`

- **修改檔案**:
  - `src/mes_dashboard/templates/wip_detail.html` - 繼承 base，使用 MesApi
  - `src/mes_dashboard/templates/wip_overview.html` - 繼承 base，使用 MesApi
  - `src/mes_dashboard/templates/index.html` - 繼承 base，使用 MesApi
  - `src/mes_dashboard/templates/portal.html` - 繼承 base
  - `src/mes_dashboard/templates/resource_status.html` - 繼承 base，使用 MesApi
  - `src/mes_dashboard/templates/excel_query.html` - 繼承 base，使用 MesApi

- **後端無變更**：此變更純前端，後端 API 保持不變
