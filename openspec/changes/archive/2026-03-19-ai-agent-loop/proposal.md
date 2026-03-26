## Why

目前 AI 助手採用固定 3-stage pipeline（意圖分類→參數填充→結果摘要），LLM 只能選擇 1 個工具且無法在資訊不足時反問使用者，導致問題模糊時經常猜錯意圖或參數，回傳無用結果。需要讓 LLM 能自主決定呼叫哪些工具、能組合多個工具回答複合問題、並在缺少必要資訊時主動向使用者要求補充。

## What Changes

- 新增**編排式 agentic loop**：系統根據 LLM 回覆動態決定下一步（呼叫工具 / 回傳答案 / 反問使用者），取代固定 3-stage 流程。每輪 LLM 呼叫仍為獨立對話，系統負責編排，不累積 messages。
- 新增**工具描述產生器**：將現有 YAML function registry（40+ 函式）轉為 prompt 內嵌的工具清單，支援兩層策略（Tier 1 常駐 + Tier 2 按需搜尋）控制 token 用量。
- 新增**工具執行分發器**：統一分發 YAML 工具、text2sql、工具搜尋的執行邏輯，回傳截斷摘要（給 LLM）和完整圖表資料（給前端）。
- 新增 **clarification 機制**：LLM 判斷資訊不足時回傳反問，response 新增 `needs_clarification` 欄位，前端以不同樣式呈現並提供建議選項。
- 透過 `AI_MODE=agent` 環境變數啟用，現有 `text2sql` / `function` 模式不受影響。
- 公開 `ai_query_service.py` 中的 `normalize_chart_data` / `summarize_for_llm` 供新模組重用。

## Capabilities

### New Capabilities
- `ai-agent-loop`: 編排式 agentic 迴圈核心 — 動態多輪工具呼叫、prompt-based tool calling 解析、防打轉防護機制
- `ai-tool-executor`: 工具執行分發器 — 統一 YAML 工具 / text2sql / 工具搜尋的執行與結果截斷
- `ai-tool-definitions`: 工具描述產生器 — YAML registry 轉 prompt 文字、兩層工具策略
- `ai-clarification-flow`: 補充資訊機制 — 後端 needs_clarification 判斷 + 前端 clarification 訊息樣式

### Modified Capabilities
<!-- 無現有 spec 的需求變更 -->

## Impact

- **後端新增 3 個模組**：`ai_agent_loop.py`、`ai_tool_executor.py`、`ai_tool_definitions.py`（均在 `src/mes_dashboard/services/`）
- **後端修改 2 個模組**：`ai_query_service.py`（公開函式 + 新 mode 分支）、`ai_function_registry.py`（新增 `build_agent_system_prompt`）
- **前端修改 2 個檔案**：`useAiChat.js`（處理 `needs_clarification`）、`AiChatPanel.vue`（clarification 樣式）
- **API response schema 擴充**：新增 `needs_clarification` 欄位（向下相容，預設 false）
- **無新增路由**：走現有 `POST /api/ai/query`
- **無新增依賴**：完全使用現有 Python/JS 套件
- **contract 更新**：`api_inventory.md` 需更新 response schema
