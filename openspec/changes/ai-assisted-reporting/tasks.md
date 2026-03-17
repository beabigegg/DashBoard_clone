## 1. Phase 1 — 異常偵測 SQL Runtime 基礎設施

- [ ] 1.1 建立 `src/mes_dashboard/sql/analytics/` 目錄，新增 SQL 模板：`yield_anomaly.sql`（Z-score 窗口函數）、`reject_spike.sql`（移動平均比較）、`hold_outlier.sql`（percentile 計算）、`equipment_deviation.sql`（OU% 偏離）
- [ ] 1.2 建立 `src/mes_dashboard/services/anomaly_detection_sql_runtime.py`，遵循 `reject_cache_sql_runtime.py` 模式：DuckDB in-memory 連線、Parquet spool 註冊、執行統計查詢
- [ ] 1.3 在 `src/mes_dashboard/core/feature_flags.py` 註冊 `ANALYTICS_ANOMALY_DETECTION_ENABLED` flag（default=False）
- [ ] 1.4 建立 `src/mes_dashboard/routes/analytics_routes.py`，實作 4 個端點：`GET /api/analytics/yield-anomalies`、`reject-spikes`、`hold-outliers`、`equipment-deviation`，使用 `success_response()` helpers 和 `configured_rate_limit()`
- [ ] 1.5 更新 `contract/api_inventory.md`，在 `standard-json` 區段新增 `analytics_routes.py`（4 個 analytics 端點）的登錄記錄

## 2. Phase 1 — 異常偵測前端整合

- [ ] 2.1 建立 `frontend/src/shared-ui/components/AnomalyBadge.vue`：接收 `count`、`items`、`type`、`loading` props；參考 `StatusBadge.vue` 的 tone 模式；使用 `state.warning` / `state.danger` 語義色彩；包含 click popover（絕對定位、top-3 項目 + 嚴重度 icon + "查看全部" 連結）；外部點擊關閉 popover；loading 時 pulse 動畫
- [ ] 2.2 在 yield-alert-center `App.vue` 整合 AnomalyBadge：`onMounted` 時以 `Promise.all` parallel 呼叫 `/api/analytics/yield-anomalies`（不阻塞主資料載入）；根據 feature flag 條件渲染；badge 置於 header `<h1>` 旁
- [ ] 2.3 在 reject-history `App.vue` 整合 AnomalyBadge，呼叫 `/api/analytics/reject-spikes`，同上整合模式
- [ ] 2.4 在 hold-overview `App.vue` 整合 AnomalyBadge，呼叫 `/api/analytics/hold-outliers`
- [ ] 2.5 在 resource-status `App.vue` 整合 AnomalyBadge，呼叫 `/api/analytics/equipment-deviation`
- [ ] 2.6 AnomalyBadge 樣式使用 `<style scoped>` + Tailwind utilities（不需獨立 CSS 檔案）；各頁面如有需要覆寫，scoped under theme class（如 `.theme-yield-alert-center`）；若有新增 CSS 檔案則更新 `contract/css_inventory.md`

## 3. Phase 1 — 測試與驗證

- [ ] 3.1 撰寫 `tests/test_anomaly_detection_sql_runtime.py`，測試各統計查詢的正確性（含邊界案例：不足 3 天資料、零標準差）
- [ ] 3.2 撰寫 `tests/test_analytics_routes.py`，測試 API 端點回應格式、feature flag 關閉時回 404、rate limit
- [ ] 3.3 用已知歷史異常資料回測，驗證 Z-score 和 percentile 偵測命中率

## 4. Phase 2 — AI 查詢後端核心

- [ ] 4.1 在 `src/mes_dashboard/core/response.py` 新增 error code 常數：`RATE_LIMIT_EXCEEDED`、`EXTERNAL_SERVICE_TIMEOUT`、`EXTERNAL_SERVICE_ERROR`
- [ ] 4.2 新增 `anthropic` Python SDK 依賴至 `pyproject.toml`（或 `requirements.txt`）
- [ ] 4.3 建立 `src/mes_dashboard/services/ai_function_registry.py`，註冊 ~20 個現有 service 函式（含 description、params schema、drill_down 關係）
- [ ] 4.4 建立 `src/mes_dashboard/services/ai_result_summarizer.py`，實作 Pareto 壓縮、趨勢壓縮、KPI 壓縮、清單摘要策略
- [ ] 4.5 建立 `src/mes_dashboard/services/ai_query_service.py`，實作：system prompt 建構（從 registry 生成）、LLM API 呼叫（Haiku/Sonnet 雙模型）、intent 驗證（白名單 + JSON schema validation）、service 函式動態調度、結果壓縮與 Level 0/1 切換
- [ ] 4.6 在 `src/mes_dashboard/core/feature_flags.py` 註冊 `AI_QUERY_ENABLED` flag（default=False）
- [ ] 4.7 新增環境變數：`AI_API_KEY`、`AI_INTENT_MODEL`（default: haiku）、`AI_SUMMARY_MODEL`（default: sonnet）、`AI_REQUEST_TIMEOUT`（default: 10s）

## 5. Phase 2 — AI 查詢 API 端點

- [ ] 5.1 建立 `src/mes_dashboard/routes/ai_routes.py`，實作 `POST /api/ai/query`（rate limit 3/min、feature flag gating、10s timeout）
- [ ] 5.2 更新 `contract/api_inventory.md`，在 `standard-json` 區段新增 `ai_routes.py`（`POST /api/ai/query`）的登錄記錄

## 6. Phase 2 — AI 查詢前端

- [ ] 6.1 建立 `frontend/src/shared-composables/useAiChat.js` composable：
  - 狀態：`messages` (ref array)、`isOpen` (ref)、`isLoading` (ref)、`isRateLimited` (ref)
  - computed `context`：從 messages 提取最近 3 輪的 intent + params + summary
  - `submitQuestion(question)`：POST `/api/ai/query`，帶 context；使用 `AbortController`（新請求取消舊請求，同 `useRequestGuard` 模式）
  - `submitSuggestion(text)`：將 suggestion 作為新問題提交
  - `resetConversation()`：清空 messages + context
  - `togglePanel()`：切換 isOpen
  - Rate limit 處理：429 時 `isRateLimited=true`，20 秒 countdown 後自動解除
- [ ] 6.2 建立 `frontend/src/shared-ui/components/AiChatTrigger.vue`：
  - 固定位置 FAB：`position: fixed; right: 24px; bottom: 24px`
  - 樣式：`w-12 h-12 rounded-full bg-brand-600 text-white shadow-shell`；hover `bg-brand-700`
  - Mobile ≤ 768px 縮小為 `w-10 h-10`
  - 面板開啟時隱藏；feature flag off 時不渲染
- [ ] 6.3 建立 `frontend/src/shared-ui/components/AiChatPanel.vue`：
  - 右側滑出面板：`position: fixed; right: 0; top: var(--shell-header-height); width: 380px; height: calc(100vh - var(--shell-header-height))`
  - 動畫：`transform: translateX(100%)` → `translateX(0)`，`--motion-normal` + `--motion-ease`
  - Z-index: 1001（高於 sidebar 的 1000）
  - 三區佈局：header（標題 + 新對話 + 關閉）/ scrollable messages / 固定底部 input bar
  - Mobile ≤ 768px：寬度 100vw + backdrop overlay
  - Escape 鍵關閉；mobile 開啟時自動關閉 sidebar
  - 背景：`bg-surface-card shadow-panel border-l border-stroke-soft`
- [ ] 6.4 建立 `frontend/src/shared-ui/components/AiChatMessage.vue`：
  - 使用者訊息：右對齊，`bg-brand-50 rounded-card p-3`
  - AI 回應：左對齊，含 explanation 文字 + `StatusBadge` tone-neutral 顯示 query type
  - 錯誤訊息：`bg-state-danger/10 text-state-danger` + retry / 一般查詢連結
  - Loading 狀態：三點動畫 typing indicator
- [ ] 6.5 建立 `frontend/src/shared-ui/components/AiChartRenderer.vue`：
  - 根據 `query_used` 自動選擇圖表類型：
    - `*_pareto` → Bar + Line 雙 Y 軸 Pareto（200px）
    - `*_trend` → Line 折線圖（180px）
    - `*_summary` / `wip_summary` → KPI 卡片 flex layout
    - `*_matrix` → mini heatmap（160px）
    - `*_list` → compact HTML table（max 10 rows, scrollable）
  - Compact 模式：隱藏 legend、簡化 tooltip、`autoresize: { throttle: 100 }`
  - ECharts import 遵循既有 `ParetoSection.vue` 模式（tree-shakable: CanvasRenderer + 需要的 Chart/Component）
- [ ] 6.6 實作 drill-down suggestion chips（在 AiChatMessage 內）：
  - 樣式：`bg-brand-50 text-brand-700 border border-brand-200 rounded-full px-3 py-1 text-sm cursor-pointer hover:bg-brand-100`
  - 點擊呼叫 `submitSuggestion(text)`
- [ ] 6.7 在 portal-shell `App.vue` 的 `.shell` 根 div 加入 `theme-portal-shell` class（啟用 CSS 合約要求的 theme scoping）
- [ ] 6.8 在 portal-shell `App.vue` 整合：
  - import `useAiChat` composable
  - 加入 `AiChatTrigger` + `AiChatPanel`
  - Shell root 加入 `:class="{ 'ai-panel-open': aiChat.isOpen.value }"`
  - Mobile 互斥邏輯：chat 開啟時自動關閉 sidebar
- [ ] 6.10 建立 `frontend/src/portal-shell/ai-chat.css`：
  - Chat panel 動畫、佈局、scrollbar 樣式
  - 所有規則 scoped under `.theme-portal-shell`
  - 更新 `contract/css_inventory.md` 登錄此檔案
- [ ] 6.11 在 `frontend/scripts/css-governance-check.js` 將 `AiChartRenderer.vue` 登錄為 ECharts HEX 色碼的 allow-candidate

## 7. Phase 2 — 測試與驗證

- [ ] 7.1 撰寫 `tests/test_ai_function_registry.py`，驗證 registry 所有 entry 指向真實存在的 service 函式，params schema 與實際函式簽名一致
- [ ] 7.2 撰寫 `tests/test_ai_result_summarizer.py`，驗證各壓縮策略的 token 產出在預算內（Pareto < 100 tokens、趨勢 < 80 tokens、清單只回傳筆數）
- [ ] 7.3 撰寫 `tests/test_ai_query_service.py`，測試 intent validation（白名單、參數 schema、日期範圍）、LLM API mock 測試、timeout 處理
- [ ] 7.4 撰寫 `tests/test_ai_routes.py`，測試端點回應格式、feature flag 關閉時 404、rate limit 429、LLM 不可用時的降級回應
- [ ] 7.5 手動測試 10 個常見自然語言查詢，驗證意圖解析正確率 > 90%
