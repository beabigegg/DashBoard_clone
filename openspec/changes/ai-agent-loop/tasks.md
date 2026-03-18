## 1. 公開現有函式供新模組重用

- [x] 1.1 將 `ai_query_service.py` 中的 `_normalize_chart_data` 改名為 `normalize_chart_data`（移除底線前綴），更新模組內所有呼叫點
- [x] 1.2 將 `ai_query_service.py` 中的 `_summarize_for_llm` 改名為 `summarize_for_llm`，更新模組內所有呼叫點
- [x] 1.3 驗證現有 `process_query_function` 和 `process_query_text2sql` 仍正常運作（跑現有 AI 相關測試）

## 2. 工具描述產生器

- [x] 2.1 建立 `src/mes_dashboard/services/ai_tool_definitions.py`，實作 `build_single_tool_description(name, entry)` — 將單一 YAML entry 轉為 prompt 文字
- [x] 2.2 實作 `build_tool_prompt_block()` — 組合 Tier 1 工具描述 + `query_database` / `search_tools` 特殊工具描述，控制在 ~1,500 tokens 內
- [x] 2.3 撰寫 `test_ai_tool_definitions.py` 單元測試：驗證 Tier 1 工具涵蓋、特殊工具存在、token 長度合理

## 3. 工具執行分發器

- [x] 3.1 建立 `src/mes_dashboard/services/ai_tool_executor.py`，實作 `execute_tool(name, arguments)` 主分發邏輯
- [x] 3.2 實作 `query_database` 特殊工具 — 委派到 `process_query_text2sql()`
- [x] 3.3 實作 `search_tools` 特殊工具 — 搜尋 REGISTRY 的 name/description 匹配 keyword
- [x] 3.4 實作 YAML 工具路由 — `validate_intent()` → `get_service_function()` → `normalize_chart_data()` → `summarize_for_llm()`，含預設參數填充
- [x] 3.5 實作錯誤捕獲 — 所有異常轉為 `{"success": False, "error": "..."}` 結構化回傳
- [x] 3.6 撰寫 `test_ai_tool_executor.py` 單元測試：mock service function，驗證各路由分支

## 4. Agent System Prompt

- [x] 4.1 在 `ai_function_registry.py` 新增 `build_agent_system_prompt()` — 組合角色設定 + 業務知識 + 工具清單 + tool_call 語法 + clarification 指引 + 回應格式 + 當前日期
- [x] 4.2 撰寫單元測試驗證 prompt 包含所有必要區段且長度在 ~4K tokens 內

## 5. Agentic Loop 核心

- [x] 5.1 建立 `src/mes_dashboard/services/ai_agent_loop.py`，實作 `process_agent_turn(question)` 編排式迴圈
- [x] 5.2 實作 `<tool_call>` regex 解析 + JSON parse + 失敗跳過邏輯
- [x] 5.3 實作 prompt 組建 — 每輪獨立 `[system, user]`，user message 包含原始問題 + 已取得結果摘要
- [x] 5.4 實作 `needs_clarification` 判斷 — 無工具呼叫 + 回覆含問號
- [x] 5.5 實作防護機制 — max 5 rounds + 同工具同參數去重
- [x] 5.6 實作 tool_trace 收集 — 每次工具執行記錄 step/function/summary/error
- [x] 5.7 實作 last_chart_data 追蹤 — 保留最後一次非 null chart_data
- [x] 5.8 撰寫 `test_ai_agent_loop.py` 單元測試：mock `_call_llm_text`，驗證單工具/多工具/clarification/max rounds/去重場景

## 6. 整合到現有 dispatch

- [x] 6.1 在 `ai_query_service.py` 的 `process_query()` 新增 `AI_MODE=agent` 分支，委派到 `process_agent_turn()`
- [x] 6.2 確保 `text2sql` / `function` 模式的 response 包含 `needs_clarification: False`（向下相容）
- [x] 6.3 跑全量 AI 測試驗證回歸

## 7. 前端 Clarification Flow

- [x] 7.1 修改 `useAiChat.js` — 解析 `needs_clarification` 欄位，設定 message role 為 `clarification`
- [x] 7.2 修改 `AiChatPanel.vue` — 為 `clarification` role 新增不同背景樣式，suggestion 按鈕保持可點擊
- [ ] 7.3 手動驗證前端：clarification 訊息樣式正確、點擊 suggestion 可送出新問題

## 8. 契約與文檔

- [x] 8.1 更新 `contract/api_inventory.md` — 記錄 `POST /api/ai/query` response 新增 `needs_clarification` 欄位
