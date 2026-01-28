# mes-api-client

統一的前端 API Client 模組，提供 timeout、retry、cancellation 功能。

## Requirements

### 核心功能

1. **統一請求入口**
   - 提供 `MesApi.get(url, options)` 用於 GET 請求
   - 提供 `MesApi.post(url, data, options)` 用於 POST 請求
   - 所有頁面必須透過此模組發送 API 請求

2. **Timeout 處理**
   - 預設 timeout: 30 秒
   - 可透過 `options.timeout` 覆蓋
   - Timeout 時自動觸發重試機制

3. **Exponential Backoff Retry**
   - 預設重試 3 次
   - 重試間隔: 1s → 2s → 4s (exponential backoff)
   - 可透過 `options.retries` 覆蓋重試次數
   - 重試時顯示 Toast 通知

4. **請求取消 (Cancellation)**
   - 支援傳入 `options.signal` (AbortController.signal)
   - 取消的請求不觸發重試，不顯示錯誤 Toast
   - Console 記錄 `⊘ Aborted`

5. **Request ID 追蹤**
   - 每個請求自動生成唯一 ID (如 `req_1a2b3c`)
   - Console log 包含 request ID，便於追蹤

### 錯誤處理

| 錯誤類型 | 重試 | Toast | 說明 |
|----------|------|-------|------|
| Timeout | ✓ | 顯示重試狀態 | 網路慢或 server 忙 |
| Network Error | ✓ | 顯示重試狀態 | fetch 失敗 |
| 5xx Server Error | ✓ | 顯示重試狀態 | Server 暫時錯誤 |
| 4xx Client Error | ✗ | 顯示錯誤 | 參數錯誤 |
| Aborted | ✗ | 無 | 使用者/程式取消 |

### Options 參數

```javascript
{
    params: Object,        // URL query parameters
    timeout: Number,       // 覆蓋預設 timeout (ms)
    retries: Number,       // 覆蓋預設重試次數
    signal: AbortSignal,   // 用於取消請求
    silent: Boolean,       // true = 不顯示 Toast
}
```

### Console Logging 格式

```
[MesApi] req_xxx GET /api/path
[MesApi] req_xxx ✓ 200 (234ms)
[MesApi] req_xxx ✗ Retry 1/3 in 1000ms
[MesApi] req_xxx ⊘ Aborted
```

## Acceptance Criteria

- [ ] `MesApi.get()` 可正常發送 GET 請求並返回 JSON
- [ ] `MesApi.post()` 可正常發送 POST 請求並返回 JSON
- [ ] Timeout 超過時自動重試，顯示 "正在重試 (N/3)..." Toast
- [ ] 重試 3 次後失敗，顯示錯誤 Toast 附帶重試按鈕
- [ ] 傳入 signal 並 abort 時，請求被取消，無錯誤 Toast
- [ ] 4xx 錯誤不重試，直接顯示錯誤
- [ ] 所有請求在 console 有 log，包含 request ID
- [ ] `options.silent = true` 時不顯示任何 Toast

## Dependencies

- `toast.js` (toast-notification capability)

## File Location

`src/mes_dashboard/static/js/mes-api.js`
