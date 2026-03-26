## Why

產線操作員和工程師目前需在 15+ 頁面間手動切換、操作多層篩選器、人工解讀圖表趨勢才能完成日常分析。異常偵測完全靠人眼判斷（良率偏移、不良率突增、Hold 時間過長、設備稼動率異常），缺乏系統化的統計警報。此外，跨領域的根因鑽研（reject → 材料 → 設備）需要多次頁面跳轉和手動關聯。引入 AI 輔助可大幅降低操作門檻並加速異常回應。

## What Changes

### Phase 1 — DuckDB 統計異常偵測（零新依賴）
- 新增 `anomaly_detection_sql_runtime.py` service，延伸現有 DuckDB-on-Parquet runtime 模式
- 新增 `analytics_routes.py` 提供異常偵測 API 端點
- 新增 `sql/analytics/*.sql` 統計查詢模板（Z-score、percentile、移動平均）
- 在現有頁面（yield-alert, reject-history, hold-overview, resource-status）加上異常標記 badge
- Feature flag `ANALYTICS_ANOMALY_DETECTION_ENABLED` 控制 rollout

### Phase 2 — LLM 自然語言查詢介面
- 新增 `ai_function_registry.py`：將 ~20 個現有 service 函式註冊為 LLM 可呼叫的能力目錄
- 新增 `ai_query_service.py`：LLM 意圖解析 → 參數驗證 → service 調度 → 結果壓縮
- 新增 `ai_result_summarizer.py`：將查詢結果壓縮為 token-efficient 摘要（Pareto 50 項 → 80 tokens）
- 新增 `ai_routes.py`：`POST /api/ai/query` 端點（rate limit 3 req/min）
- 前端 Portal shell 新增 chat 輸入元件，支援多輪對話上下文
- 後端代理模式（API key 不上前端、無需 CSP 變更）
- 三級 token 策略：Level 0 純意圖解析（~3K tokens/次）、Level 1 壓縮摘要（~5K tokens/次）

## Capabilities

### New Capabilities
- `anomaly-detection-runtime`: DuckDB 統計異常偵測引擎 — 良率 Z-score、不良率突增、Hold 離群值、設備稼動偏離
- `ai-query-interface`: LLM 自然語言查詢介面 — function registry、意圖解析、結果壓縮、多輪對話
- `ai-query-frontend`: 前端 AI 查詢元件 — Portal shell 內的 chat UI、對話上下文管理、圖表渲染

### Modified Capabilities
- `yield-alert-center-page`: 新增異常偵測 badge 顯示 Z-score 超標項目
- `reject-history-page`: 新增不良率突增警示標記
- `hold-overview-page`: 新增 Hold 時間離群值標記
- `resource-status-page`: 新增設備稼動偏離標記

## Impact

**後端：**
- 新增 3 個 service 模組 + 1 個 route 模組 + SQL 模板目錄
- 新增 `anthropic` 或 `openai` Python SDK 依賴（Phase 2）
- API inventory 需登錄 ~5 個新端點（`standard-json` 分類）
- 記憶體影響：Phase 1 極小（延伸 DuckDB）；Phase 2 極小（僅 HTTP 請求）

**前端：**
- Portal shell 右側新增 AI Chat 滑出面板（Phase 2）— 目前 shell 僅有左側 sidebar，此為首個右側面板元件
- 新增 `AiChatPanel.vue`（滑出面板 + 對話歷史 + 內嵌 ECharts 圖表渲染）
- 新增 `AiChatTrigger.vue`（固定位置觸發按鈕）
- 新增 `useAiChat.js` composable（對話狀態管理、context 累積、API 呼叫、rate limit UI 鎖定）
- 新增 `AnomalyBadge.vue` 共用元件（Phase 1）— 擴展現有 `StatusBadge.vue` 的 tone 模式，加入 popover 展開
- 4 個現有頁面（yield-alert, reject-history, hold-overview, resource-status）整合 AnomalyBadge
- CSS inventory 需登錄新樣式檔（chat 面板樣式 scoped under `.theme-portal-shell`）

**基礎設施：**
- Phase 2 需外部網路連線至 LLM API（需資安審查）
- CSP 無需變更（後端代理模式）
- 預估 API 成本：$0.10-0.50/天（Haiku 意圖解析 + Sonnet 摘要分析混合）

**治理：**
- 所有新端點遵循 API 合約（response helpers、route/service 分離）
- Feature flag 控制每個階段的 rollout
- 製造資料不傳送至外部 LLM（僅意圖解析模式）
