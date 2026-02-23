## ADDED Requirements

### Requirement: Released Query APIs SHALL Return 4xx for Invalid JSON Inputs
Released 頁面對應的 JSON API 在收到非 JSON、Malformed JSON、或型別不符 payload 時，MUST 回覆可預期的 4xx 錯誤，且 MUST NOT 因 JSON 解析失敗回落為 500。

#### Scenario: Non-JSON request to JSON-only endpoint
- **WHEN** client 以 `Content-Type: text/plain` 或缺少 JSON body 呼叫 JSON-only endpoint（例如 `/api/query-tool/*`、`/api/job-query/*`、`/api/resource/detail`）
- **THEN** endpoint MUST 回覆 400 或 415，並提供一致的錯誤訊息
- **THEN** service layer MUST NOT 執行高成本查詢

#### Scenario: Malformed JSON payload
- **WHEN** client 送出無法解析的 JSON 內容
- **THEN** endpoint MUST 回覆 400
- **THEN** response MUST 指出 payload 格式錯誤，而非 generic 500

### Requirement: High-Cost Batch Inputs SHALL Enforce Hard Upper Bounds
Released 頁面高成本查詢端點 MUST 對批量輸入與查詢筆數上限施加硬限制，避免單次請求造成過量資料讀取或計算。

#### Scenario: Query-tool batch container IDs exceed limit
- **WHEN** `container_ids` 數量超過設定上限
- **THEN** endpoint MUST 回覆 400 或 413，且 MUST 附帶可操作的上限資訊
- **THEN** backend MUST NOT 執行 Oracle/Redis 高成本查詢流程

#### Scenario: Resource detail limit exceeds limit
- **WHEN** `/api/resource/detail` 的 `limit` 超過設定上限
- **THEN** endpoint MUST 拒絕請求或安全夾制至上限，並在契約中明確定義行為
- **THEN** response 行為 MUST 於測試中固定化，避免版本漂移

### Requirement: Rate-Limit Client Identity SHALL Respect Trust Boundary
Rate limiting 的 client identity 解析 MUST 依部署信任邊界運作，未啟用 trusted proxy 時 MUST NOT 直接信任 `X-Forwarded-For`。

#### Scenario: Direct internet deployment without reverse proxy
- **WHEN** 服務直接對外且未啟用 trusted proxy 模式
- **THEN** rate-limit key MUST 使用 `remote_addr`（或等價來源）
- **THEN** 來自 request header 的 `X-Forwarded-For` MUST 被忽略

#### Scenario: Deployment with trusted reverse proxy enabled
- **WHEN** 系統明確配置 trusted proxy 名單或模式
- **THEN** rate-limit key MAY 使用 `X-Forwarded-For` 的可信 client IP
- **THEN** 非可信來源 MUST 回退至 `remote_addr`

### Requirement: Production Security Defaults SHALL Fail Safe
生產設定在缺漏或格式錯誤時 MUST 採 fail-safe 預設，避免 API 無意外暴露或低安全模式啟動。

#### Scenario: page status config missing or invalid
- **WHEN** `page_status.json` 缺失、破損或缺少 `api_public` 設定
- **THEN** runtime MUST 預設為 API 非公開（`api_public=false`）
- **THEN** 需要明確配置才可開啟公開 API 行為

#### Scenario: runtime environment variables incomplete
- **WHEN** 生產啟動缺少關鍵安全變數（例如 `SECRET_KEY`）
- **THEN** 系統 MUST 以安全方式拒絕啟動或進入受限模式，且輸出可診斷訊息

### Requirement: Sensitive Configuration Values SHALL Be Redacted in Logs
任何含憑證的連線字串（例如 Redis URL）在 log 輸出時 MUST 進行遮罩，避免密碼外洩。

#### Scenario: Redis URL includes password
- **WHEN** 應用程式記錄 Redis 連線設定
- **THEN** log 中的 URL MUST 隱藏密碼（例如 `redis://***@host:port/db`）
- **THEN** 原始明文密碼 MUST NOT 出現在任何應用層日誌

### Requirement: Released Frontend Views SHALL Avoid Unsafe Inline Interpolation
Released 頁面前端 MUST 避免將不受信資料直接插入 inline JavaScript 或 HTML 屬性字串，降低 XSS 與 handler 斷裂風險。

#### Scenario: Rendering action controls with user-derived values
- **WHEN** 前端渲染按鈕或互動控制（例如 job-query 操作欄）且內容含資料列值
- **THEN** MUST 透過安全資料綁定（data-* attribute 或事件監聽）實作
- **THEN** MUST NOT 依賴 raw string `onclick="...${value}..."` 拼接

### Requirement: Released Hardening SHALL Be Protected by Regression Gates
本次 hardening 的行為 MUST 由自動化測試固定，並納入 CI gate，避免日後回歸。

#### Scenario: Negative-path regression suite execution
- **WHEN** CI 執行 Released 頁面 API 測試
- **THEN** MUST 覆蓋 invalid JSON、超量輸入、rate-limit、security default、與 log redaction 斷言
- **THEN** 任一關鍵斷言失敗 MUST 阻擋合併

#### Scenario: Existing released behavior parity
- **WHEN** hardening 變更部署後執行既有 Released route 測試
- **THEN** 成功路徑與既有回應契約 MUST 維持相容
- **THEN** 僅新增已定義的防護錯誤路徑（4xx/429）
