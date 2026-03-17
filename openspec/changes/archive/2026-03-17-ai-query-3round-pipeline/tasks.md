## 1. YAML 函式註冊表

- [x] 1.1 確認 PyYAML 是否為既有依賴；若無，加入 `requirements.txt`
- [x] 1.2 建立 `src/mes_dashboard/services/ai_functions.yaml`：將現有 `REGISTRY` dict 的 16 個函式轉為 YAML 格式，頂部含 `_enums.WORKCENTER_GROUPS`，每個函式含 description、service、chart_type、params、drill_down
- [x] 1.3 重寫 `src/mes_dashboard/services/ai_function_registry.py`：
  - `_load_registry()` — 載入 YAML、展開 `$ENUM` 引用、回傳 dict
  - `REGISTRY = _load_registry()` — 模組層級載入
  - 保留 `validate_intent()`、`get_service_function()`、`get_suggestions()`（邏輯不變，只是資料來源改 YAML）
  - 移除舊的 `build_system_prompt()`，改為三個新 prompt builder（見 task 1.4）
- [x] 1.4 在 `ai_function_registry.py` 新增三個 prompt builder：
  - `build_round1_prompt()` — 精簡函式列表（名稱+描述，~400-500 tokens）
  - `build_round2_prompt(function_name)` — 單一函式完整 schema + enum + 日期規則 + 站別列表
  - `build_round3_prompt()` — 固定分析指引（直接回答、2-3 關鍵數據、不超過 5 句、不要 JSON）

## 2. 後端三輪 Pipeline

- [x] 2.1 重寫 `src/mes_dashboard/services/ai_query_service.py`：
  - 移除：`_get_conversation`、`_save_conversation`、`_conversation_key`、`_new_conversation_id`、`_estimate_tokens`、`_AI_MAX_ROUNDS`、`_AI_CONTEXT_TOKEN_LIMIT`、`_AI_CONVERSATION_TTL`、OverflowError 相關邏輯
  - 修改 `_call_llm(messages, max_tokens=None)` — 新增 max_tokens 參數
  - 新增 `_call_llm_text(messages, max_tokens=None) -> str` — 回傳原始文字，不解析 JSON
  - 新增 `_summarize_for_llm(function_name, chart_data, max_chars=4500) -> str` — 按 chart_type 截斷結果
  - 重寫 `process_query(question: str) -> dict` — 三輪 pipeline（R1 意圖 → R2 參數 → 執行 → R3 摘要）
  - 保留 `_normalize_chart_data()` 不變
- [x] 2.2 簡化 `src/mes_dashboard/routes/ai_routes.py`：
  - 移除 `conversation_id` 解析、`user_id` from session、`OverflowError` handler
  - `process_query(question)` 只傳 question
  - Response 不含 `conversation_id`、`round`、`max_rounds`
- [x] 2.3 簡化 `src/mes_dashboard/config/settings.py`：移除 `AI_MAX_ROUNDS`、`AI_CONTEXT_TOKEN_LIMIT`、`AI_CONVERSATION_TTL`
- [x] 2.4 更新 `.env.example`：移除上述三項配置

## 3. 前端重構

- [x] 3.1 簡化 `frontend/src/shared-composables/useAiChat.js`：
  - 移除：`conversationId`、`currentRound`、`maxRounds`、`isContextFull`、`CONTEXT_LIMIT_REACHED` 處理、request 中 `conversation_id`、response 中 `conversation_id/current_round/max_rounds` 解析
  - `resetConversation()` → `clearHistory()`（只清 messages）
  - `canSubmit` 簡化為 `!isLoading && !isRateLimited`
  - 新增 `loadingStepText` ref + `setInterval` 計時器（每 3 秒切換步驟文字）
  - Expose `loadingStepText`
- [x] 3.2 更新 `frontend/src/shared-ui/components/AiChatPanel.vue`：
  - 移除 props：`conversationId`、`currentRound`、`maxRounds`、`isContextFull`
  - 移除 header 的 `N/5` 輪次顯示
  - 「新對話」按鈕 → 「清除紀錄」按鈕（emit `reset`）
  - 移除 input bar 的 context 上限提示
  - 新增 prop `loadingStepText`，傳到 loading 區域
  - 新增對話分隔線：在前一則 ai + 下一則 user 之間插入 `.ai-conversation-divider`
- [x] 3.3 更新 `frontend/src/shared-ui/components/AiChatMessage.vue`：
  - Loading 區塊加 `stepText` prop，在三點動畫旁顯示步驟文字
  - 移除 `isContextFull` prop 對 suggestion chips 的 disabled 控制
- [x] 3.4 更新 `frontend/src/portal-shell/App.vue`：
  - 移除傳給 AiChatPanel 的 `conversationId`、`currentRound`、`maxRounds`、`isContextFull` props
  - 新增 `loadingStepText` prop binding
  - `@reset` handler 對應 `clearHistory`
- [x] 3.5 更新 `frontend/src/portal-shell/ai-chat.css`：
  - 新增 `.ai-step-text` 樣式（scoped under `.theme-portal-shell`）
  - 新增 `.ai-conversation-divider`、`.ai-divider-line`、`.ai-divider-text` 樣式

## 4. 測試更新

- [x] 4.1 更新 `tests/test_ai_function_registry.py`：
  - 新增 `TestYamlLoading` — YAML 載入、enum 展開、所有 service path 可 import
  - 新增 `TestBuildRound1Prompt` — 所有函式名出現、無參數細節
  - 新增 `TestBuildRound2Prompt` — 只含指定函式的參數、含 enum
  - 新增 `TestBuildRound3Prompt` — 無 JSON 指令、含分析規則
  - 保留 `TestValidateIntent`、`TestGetSuggestions`（適配 YAML 資料來源）
- [x] 4.2 更新 `tests/test_ai_query_service.py`：
  - 移除 `TestGetConversation`、`TestSaveConversation`、`TestProcessQueryContextLimit`
  - 更新 `TestProcessQueryValidIntent` — mock `_call_llm` 為 `side_effect` list（R1 intent, R2 params, R3 text）
  - 新增 `TestRound3Fallback` — Round 3 失敗仍回傳 chart_data + fallback 文字
  - 新增 `TestSummarizeForLlm` — 各 chart type 截斷測試
  - 保留 `TestProcessQueryLLMErrors`、`TestProcessQueryNullIntent`
- [x] 4.3 更新 `tests/test_ai_routes.py`：
  - 移除 conversation_id 相關、OverflowError / CONTEXT_LIMIT_REACHED 測試
  - 保留 feature flag、validation、success、timeout/connection error 測試
- [x] 4.4 執行 `pytest tests/ -v` 確認全部測試通過

## 5. 合約與文件更新

- [x] 5.1 更新 `contract/api_inventory.md` — 更新 POST /api/ai/query 說明（移除 conversation_id）
- [x] 5.2 驗證 `contract/css_inventory.md` — ai-chat.css 已登錄（無需變更）
