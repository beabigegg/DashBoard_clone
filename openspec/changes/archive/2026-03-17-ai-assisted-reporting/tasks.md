## 1. Phase 1 — 異常偵測 SQL Runtime 基礎設施 ✅ 已完成

- [x] 1.1 建立 `src/mes_dashboard/sql/analytics/` 目錄，新增 SQL 模板：`yield_anomaly.sql`、`reject_spike.sql`、`hold_outlier.sql`、`equipment_deviation.sql`
- [x] 1.2 建立 `src/mes_dashboard/services/anomaly_detection_sql_runtime.py`
- [x] 1.3 在 `src/mes_dashboard/core/feature_flags.py` 註冊 `ANALYTICS_ANOMALY_DETECTION_ENABLED` flag
- [x] 1.4 建立 `src/mes_dashboard/routes/analytics_routes.py`
- [x] 1.5 更新 `contract/api_inventory.md`

## 2. Phase 1 — 異常偵測前端整合 ✅ 已完成

- [x] 2.1~2.6 AnomalyBadge + 各頁面整合

## 3. Phase 1 — 測試與驗證 ✅ 已完成

- [x] 3.1~3.3 測試已通過

## 4. Phase 2 — AI 查詢後端配置 ✅ 已完成

- [x] 4.1 在 `core/response.py` 新增 error code 常數：`EXTERNAL_SERVICE_TIMEOUT`、`EXTERNAL_SERVICE_ERROR`、`CONTEXT_LIMIT_REACHED`，並新增對應的 convenience functions `external_service_timeout_error()`、`external_service_error()`、`context_limit_error()`
- [x] 4.2 在 `config/settings.py` 的 `Config` class 新增 AI 相關配置項：
  - `AI_QUERY_ENABLED`（default=False，使用 `_bool_env`）
  - `AI_API_URL`（default=`https://ollama_pjapi.theaken.com`）
  - `AI_API_KEY`（from env, no default）
  - `AI_MODEL`（default=`gpt-oss:120b`）
  - `AI_REQUEST_TIMEOUT`（default=30）
  - `AI_VERIFY_TLS`（default=False）
  - `AI_MAX_ROUNDS`（default=5）
  - `AI_CONTEXT_TOKEN_LIMIT`（default=12000）
  - `AI_MAX_TOKENS`（default=500）
  - `AI_CONVERSATION_TTL`（default=1800）
- [x] 4.3 在 `.env` 新增 `AI_QUERY_ENABLED=true`、`AI_API_KEY=<actual key>`，以及其他 AI 相關項（使用預設值的可省略）
- [x] 4.4 在 `.env.example` 新增 AI 相關環境變數區塊（`AI_API_KEY` 使用 placeholder `your-ai-api-key`），格式與現有區塊一致

## 5. Phase 2 — AI 查詢後端核心 ✅ 已完成

- [x] 5.1 建立 `src/mes_dashboard/services/ai_function_registry.py`：
  - 定義 `REGISTRY` dict，包含 ~15 個函式 entry（每個 entry 含 description, service 函式路徑, params schema, drill_down）
  - 覆蓋領域：reject（pareto, trend, spike alerts）、yield（anomaly alerts, detail）、WIP（summary, matrix, hold summary）、Hold（outlier alerts, history trend, reason pareto）、equipment（deviation alerts, status summary）、lot query、equipment recent jobs
  - 實作 `build_system_prompt()` — 從 REGISTRY 動態生成 system prompt，含回覆格式指示、參數說明、workcenter group 代碼列表
  - 實作 `validate_intent(function_name, params)` — 檢查函式是否存在於 REGISTRY、參數是否符合 schema（type, required, enum）
  - 實作 `get_service_function(function_name)` — 動態 import 並回傳對應的 service 函式
  - 實作 `get_suggestions(function_name)` — 從 drill_down 生成中文 suggestion 文字列表

- [x] 5.2 建立 `src/mes_dashboard/services/ai_query_service.py`：
  - 實作 Redis 對話管理：
    - `_get_conversation(user_id, conversation_id)` — 從 Redis 讀取對話 `ai_chat:{user_id}:{conversation_id}`
    - `_save_conversation(user_id, conversation_id, messages, round_count)` — 寫入 Redis + TTL refresh
    - `_new_conversation_id()` — 生成 UUID
  - 實作 `_call_llm(messages)` — `requests.post` 呼叫 LLM API
    - URL: `{AI_API_URL}/v1/chat/completions`
    - Headers: `Authorization: Bearer {AI_API_KEY}`, `Content-Type: application/json`
    - Body: `{ model: AI_MODEL, messages, stream: false, max_tokens: AI_MAX_TOKENS }`
    - `verify=AI_VERIFY_TLS`, `timeout=AI_REQUEST_TIMEOUT`
    - 回應解析：`content = msg.get("content") or msg.get("reasoning_content")`
    - JSON 提取：先 `json.loads(content)`，失敗則正則 `re.search(r'\{.*\}', content, re.DOTALL)`
  - 實作 `_estimate_tokens(messages)` — 簡易 token 估算（中文 ~1.5 chars/token, 英文 ~4 chars/token），用於 context 上限偵測
  - 實作 `process_query(user_id, question, conversation_id=None)` — 主入口函式（見 design.md 對話流程）
  - 錯誤處理：
    - `requests.Timeout` → `EXTERNAL_SERVICE_TIMEOUT`
    - `requests.ConnectionError` / HTTP 5xx → `EXTERNAL_SERVICE_ERROR`
    - round_count > AI_MAX_ROUNDS → `CONTEXT_LIMIT_REACHED`
    - estimated tokens > AI_CONTEXT_TOKEN_LIMIT → `CONTEXT_LIMIT_REACHED`
    - intent validation 失敗 → `VALIDATION_ERROR`

- [x] 5.3 建立 `src/mes_dashboard/routes/ai_routes.py`：
  - Blueprint `ai_bp`
  - `configured_rate_limit` 使用 `AI_RATE_LIMIT_MAX_REQUESTS` / `AI_RATE_LIMIT_WINDOW_SECONDS`（default 3/60）
  - `POST /api/ai/query`：
    - Feature flag gating（`AI_QUERY_ENABLED`）→ 關閉時 `not_found_error("功能未啟用")`
    - 解析 JSON body `{ question: str, conversation_id?: str }`
    - 從 session 取得 user_id
    - 呼叫 `ai_query_service.process_query(user_id, question, conversation_id)`
    - 成功 → `success_response(data)`
    - 各類錯誤 → 對應的 error response helpers

- [x] 5.4 在 `routes/__init__.py` 新增 `from .ai_routes import ai_bp` 和 `app.register_blueprint(ai_bp)`，更新 `__all__`

## 6. Phase 2 — 合約與文件更新 ✅ 已完成

- [x] 6.1 更新 `contract/api_inventory.md`，在 `standard-json` 區段新增 `ai_routes.py`（`POST /api/ai/query`）
- [x] 6.2 完成後端實作後，執行 `pytest tests/ -v` 確認既有測試不受影響

## 7. Phase 2 — AI 查詢前端 ✅ 已完成

- [x] 7.1 建立 `frontend/src/shared-composables/useAiChat.js` composable：
  - 狀態：`messages` (ref array), `conversationId` (ref), `currentRound` (ref), `maxRounds` (ref, default 5), `isOpen` (ref), `isLoading` (ref), `isRateLimited` (ref), `isContextFull` (ref)
  - `submitQuestion(question)` — POST `/api/ai/query` 帶 `{ question, conversation_id }`
    - 使用 `AbortController`（新請求取消舊請求）
    - 成功 → push user message + AI message 至 `messages`；更新 `conversationId`, `currentRound`, `maxRounds`
    - 收到 `CONTEXT_LIMIT_REACHED` → `isContextFull = true`
    - 收到 429 → `isRateLimited = true`，20 秒 countdown 後自動解除
    - 其他錯誤 → push error message 至 `messages`
  - `submitSuggestion(text)` — 將 suggestion 作為新問題提交
  - `resetConversation()` — 清空 `messages`, `conversationId`, `currentRound`, `isContextFull`
  - `togglePanel()` — 切換 `isOpen`
  - computed `canSubmit` — `!isLoading && !isRateLimited && !isContextFull && currentRound < maxRounds`

- [x] 7.2 建立 `frontend/src/shared-ui/components/AiChatTrigger.vue`：
  - 固定位置 FAB：`position: fixed; right: 24px; bottom: 24px`
  - 樣式：`w-12 h-12 rounded-full bg-brand-600 text-white shadow-shell`；hover `bg-brand-700`
  - Mobile ≤ 768px 縮小為 `w-10 h-10`
  - 面板開啟時隱藏（由 App.vue 的 `v-if` 控制）
  - 含 AI icon（SVG inline）

- [x] 7.3 建立 `frontend/src/shared-ui/components/AiChatPanel.vue`：
  - 右側滑出面板：`position: fixed; right: 0; top: var(--shell-header-height); width: 380px; height: calc(100vh - var(--shell-header-height))`
  - 動畫：`transform: translateX(100%)` → `translateX(0)`，`--motion-normal` + `--motion-ease`
  - Z-index: 1001
  - 三區佈局：
    - Header：標題「AI 助手」+ 輪次顯示「N/5」+ 「新對話」按鈕 + 關閉按鈕
    - Scrollable messages area（自動捲動至底部）
    - Fixed bottom input bar：
      - textarea（支援 Enter 送出，Shift+Enter 換行）
      - Send button
      - `isContextFull` 或 `currentRound >= maxRounds` 時 disabled + 提示文字「對話已達上限，請開啟新對話」
      - `isRateLimited` 時 disabled + countdown 顯示
  - Mobile ≤ 768px：寬度 100vw + backdrop overlay
  - Escape 鍵關閉；mobile 開啟時自動關閉 sidebar
  - 背景：`bg-surface-card shadow-panel border-l border-stroke-soft`

- [x] 7.4 建立 `frontend/src/shared-ui/components/AiChatMessage.vue`：
  - 使用者訊息：右對齊，`bg-brand-50 rounded-card p-3`
  - AI 回應：左對齊，含：
    - explanation 文字
    - query_used 標籤（StatusBadge tone-neutral）
    - AiChartRenderer（如有 chart_data）
    - drill-down suggestion chips
  - 錯誤訊息：`bg-state-danger/10 text-state-danger` + retry 按鈕
  - Loading 狀態：三點動畫 typing indicator
  - Context 上限訊息：「對話已達上限，請點擊「新對話」繼續」

- [x] 7.5 建立 `frontend/src/shared-ui/components/AiChartRenderer.vue`：
  - 根據 `query_used` 自動選擇圖表類型（見 design.md 圖表渲染策略表）
  - Compact 模式：隱藏 legend、簡化 tooltip、`autoresize: { throttle: 100 }`
  - ECharts import 遵循既有 `ParetoSection.vue` 模式（tree-shakable）
  - ECharts HEX 色碼集中在單一 palette 物件

- [x] 7.6 實作 drill-down suggestion chips（在 AiChatMessage 內）：
  - 樣式：`bg-brand-50 text-brand-700 border border-brand-100 rounded-full px-3 py-1 text-sm cursor-pointer hover:bg-brand-100`
  - 點擊呼叫 `submitSuggestion(text)`
  - `isContextFull` 時 chips disabled

- [x] 7.7 建立 `frontend/src/portal-shell/ai-chat.css`：
  - Chat panel 動畫、佈局、scrollbar 樣式
  - 所有規則 scoped under `.theme-portal-shell`
  - Typing indicator 動畫

- [x] 7.8 在 portal-shell `App.vue` 整合：
  - 在 `.shell` 根 div 加入 `theme-portal-shell` class
  - import `useAiChat` composable
  - 加入 `AiChatTrigger` + `AiChatPanel`（feature flag gating 由後端 API 控制，前端可加 `/api/portal/navigation` 的 feature flag 檢查或直接渲染）
  - Shell root 加入 `:class="{ 'ai-panel-open': aiChat.isOpen.value }"`
  - Mobile 互斥邏輯：chat 開啟時自動關閉 sidebar

- [x] 7.9 在 `frontend/scripts/css-governance-check.js` 將 `AiChartRenderer.vue` 登錄為 ECharts HEX 色碼的 allow-candidate

- [x] 7.10 更新 `contract/css_inventory.md` 登錄 `frontend/src/portal-shell/ai-chat.css`

## 8. Phase 2 — 測試與驗證

- [x] 8.1 撰寫 `tests/test_ai_function_registry.py`：驗證 REGISTRY 所有 entry 指向真實存在的 service 函式；params schema 與實際函式簽名一致；`build_system_prompt()` 輸出非空；`validate_intent()` 正確攔截無效函式和參數
- [x] 8.2 撰寫 `tests/test_ai_query_service.py`：測試 intent validation、conversation Redis CRUD、LLM API mock 測試、timeout 處理、context 上限偵測、round 超限處理
- [x] 8.3 撰寫 `tests/test_ai_routes.py`：測試端點回應格式、feature flag 關閉時 404、rate limit 429
- [ ] 8.4 手動測試 10 個常見自然語言查詢（含多輪對話），驗證意圖解析正確率 > 90%
- [ ] 8.5 測試 5 輪對話完整流程：建立對話 → 追問 4 次 → 第 6 次收到上限提示 → 新對話正常運作
