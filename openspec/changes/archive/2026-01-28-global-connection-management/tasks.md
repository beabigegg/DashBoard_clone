# Implementation Tasks

## Phase 1: 建立基礎設施

### 1.1 建立目錄結構
- [x] 建立 `src/mes_dashboard/static/` 目錄
- [x] 建立 `src/mes_dashboard/static/js/` 目錄

### 1.2 建立 toast.js
- [x] 實作 Toast 物件，包含 info/success/warning/error/loading 方法
- [x] 實作 Toast.update() 方法
- [x] 實作 Toast.dismiss() 方法
- [x] 實作最大 5 個 Toast 限制
- [x] 實作進入/離開動畫

### 1.3 建立 mes-api.js
- [x] 實作 MesApi.get() 方法
- [x] 實作 MesApi.post() 方法
- [x] 實作 timeout 處理 (預設 30s)
- [x] 實作 exponential backoff retry (1s → 2s → 4s)
- [x] 實作 AbortController signal 支援
- [x] 實作 request ID 生成與 console logging
- [x] 整合 Toast 通知（重試中、失敗）

### 1.4 建立 _base.html
- [x] 建立 base template 結構
- [x] 定義 title / head_extra / content / scripts blocks
- [x] 內嵌 Toast CSS 樣式
- [x] 引入 toast.js 和 mes-api.js
- [x] 加入 Toast 容器 `#mes-toast-container`

### 1.5 驗證基礎設施
- [x] 確認 Flask 正確服務 static 檔案
- [x] 建立自動化測試驗證 MesApi 和 Toast 運作

---

## Phase 2: 遷移 WIP 頁面

### 2.1 遷移 wip_detail.html
- [x] 改用 `{% extends "_base.html" %}`
- [x] 移除內嵌的 `fetchWithTimeout` 函數
- [x] 移除內嵌的 AbortController 管理變數
- [x] 將 `fetch()` 呼叫改為 `MesApi.get()`
- [x] 保留 AbortController 用於請求取消（傳入 signal）
- [x] 移除手動的錯誤 toast 顯示邏輯
- [x] 測試：E2E 測試驗證頁面載入、Toast 和 MesApi 功能

### 2.2 遷移 wip_overview.html
- [x] 改用 `{% extends "_base.html" %}`
- [x] 移除內嵌的 `fetchWithTimeout` 函數
- [x] 移除內嵌的 AbortController 管理變數
- [x] 將 `fetch()` 呼叫改為 `MesApi.get()`
- [x] 保留 AbortController 用於請求取消（傳入 signal）
- [x] 移除手動的錯誤 toast 顯示邏輯
- [x] 測試：E2E 測試驗證頁面載入、Toast 和 MesApi 功能

---

## Phase 3: 遷移其他頁面

### 3.1 遷移 index.html (Tables)
- [x] 改用 `{% extends "_base.html" %}`
- [x] 將 `fetch()` 呼叫改為 `MesApi.post()`
- [x] 加入錯誤處理（之前沒有）
- [x] 測試：E2E 測試驗證頁面載入、Toast 和 MesApi 功能

### 3.2 遷移 resource_status.html
- [x] 改用 `{% extends "_base.html" %}`
- [x] 將 `fetch()` 呼叫改為 `MesApi.get()` / `MesApi.post()`
- [x] 測試：E2E 測試驗證頁面載入、Toast 和 MesApi 功能

### 3.3 遷移 excel_query.html
- [x] 改用 `{% extends "_base.html" %}`
- [x] 將 `fetch()` 呼叫改為 `MesApi.post()`
- [x] 保留 native fetch 用於 FormData 上傳和 blob 下載
- [x] 測試：E2E 測試驗證頁面載入、Toast 和 MesApi 功能

### 3.4 遷移 portal.html
- [x] 改用 `{% extends "_base.html" %}`
- [x] 確認 iframe 載入不受影響
- [x] 測試：E2E 測試驗證 Tab 切換

---

## Phase 4: 最終驗證

### 4.1 整合測試
- [x] 測試所有頁面正常運作（61 個自動化測試通過）
- [x] E2E 測試驗證 Toast 通知系統
- [x] E2E 測試驗證 MesApi 客戶端

### 4.2 Console Log 驗證
- [x] 確認所有請求有 `[MesApi] req_xxx` log（E2E 測試驗證）
- [x] 確認成功顯示 `✓`，重試顯示 `✗ Retry`，取消顯示 `⊘`

### 4.3 清理
- [x] 移除任何遺留的舊 fetchWithTimeout 程式碼
- [x] 確認沒有直接使用 `fetch()` 的 API 呼叫（除非有特殊原因）

---

## 測試覆蓋

### 單元測試 (17 tests)
- tests/test_template_integration.py
  - 驗證所有頁面引入 toast.js 和 mes-api.js
  - 驗證 Toast CSS 樣式已內嵌
  - 驗證 MesApi 使用於各頁面
  - 驗證靜態檔案正確服務

### 整合測試 (12 tests)
- tests/test_api_integration.py
  - 驗證 API 回應格式
  - 驗證錯誤處理
  - 驗證 Content-Type

### E2E 測試 (32 tests)
- tests/e2e/test_global_connection.py
  - Portal 頁面載入和 Tab 切換
  - Toast 通知系統 (info/success/error/loading/dismiss/max limit)
  - MesApi 客戶端 (get/post/logging)
  - 所有 6 個頁面載入並包含 Toast 和 MesApi
  - Console log 驗證 request ID

---

## 完成標準

- [x] 所有 6 個頁面使用 `{% extends "_base.html" %}`
- [x] 所有 API 請求透過 `MesApi` 發送
- [x] 錯誤時自動重試並顯示 Toast
- [x] 重試失敗時顯示手動重試按鈕
- [x] Console 有完整的請求追蹤 log
- [x] 61 個自動化測試全部通過
