## Context

AI 助手目前使用固定 3-stage pipeline（`process_query_function` / `process_query_text2sql`），每輪 LLM 呼叫獨立，系統負責編排。此架構的核心限制是：只能選 1 個工具、無法反問使用者、無法組合多工具回答。

現有基礎設施：
- LLM：內部 gpt-oss:120b，OpenAI-compatible API，16K context，不支援原生 tools 參數
- 工具：40+ YAML 函式（`ai_functions.yaml`）+ text2sql pipeline
- 前端：Vue 3 chat panel（`AiChatPanel.vue` + `useAiChat.js`）

## Goals / Non-Goals

**Goals:**
- LLM 能在一次 request 內自主呼叫 0~N 個工具，再統整回答
- LLM 能在資訊不足時反問使用者，而非硬猜
- 每輪 LLM 呼叫保持獨立（不累積 messages），token 用量穩定在 ~7K/輪
- 透過 `AI_MODE=agent` 啟用，不影響現有 `text2sql` / `function` 模式

**Non-Goals:**
- 跨 request 的對話記憶（Phase 3）
- 持久化業務知識庫（Phase 3, MySQL）
- LLM streaming（現有架構不支援）
- 原生 OpenAI function calling（模型不支援）

## Decisions

### Decision 1: 編排式 vs. 累積式對話

**選擇：編排式** — 每輪 LLM 呼叫為獨立全新對話，系統將已取得的工具結果摘要拼入 user message。

**替代方案：累積式** — 所有 messages 逐輪累積（system → user → assistant → tool_result → assistant → ...）。

**理由**：
- 16K context 下，累積式 3 輪就會爆（system 4K + 每輪 tool result 2K = 10K+）
- 編排式每輪穩定 ~7K，完全不需要壓縮機制
- 與現有架構哲學一致（現有 3-stage 也是每輪獨立）
- LLM 不需要知道自己前一輪說了什麼 — 它只需要看到問題 + 已有結果，決定下一步

### Decision 2: Prompt-based tool calling 格式

**選擇：`<tool_call>{"name":"...","arguments":{...}}</tool_call>` XML 標記**

**替代方案：** 純 JSON output、Markdown code block、自然語言解析。

**理由**：
- XML 標記有明確的開始/結束界定，regex 解析可靠
- LLM 可以在 tool_call 標記外寫自然語言（解釋推理過程），不衝突
- 開源 120B 模型對 XML 標記的遵循率優於純 JSON 格式

### Decision 3: 兩層工具策略（Tier 1 + Tier 2）

**選擇：** Tier 1 常駐 8-10 個高頻工具在 system prompt，Tier 2 透過 `search_tools` meta-tool 按需發現。

**替代方案：** 全部 40+ 工具塞進 prompt。

**理由**：
- 40+ 工具描述約 3K-4K tokens，加上業務知識就超過 system prompt 預算
- 80/20 法則：~8 個高頻工具覆蓋大部分查詢
- `search_tools` 讓 LLM 能自主發現冷門工具，不犧牲覆蓋率

### Decision 4: Clarification 判斷邏輯

**選擇：** 後端根據「未執行任何工具 + 回覆含問號」判定 `needs_clarification=true`。

**替代方案：** 在 system prompt 中指示 LLM 輸出特殊標記（如 `<clarification>`）。

**理由**：
- 減少對 LLM 格式遵循的依賴
- 簡單規則已足夠：如果 LLM 沒呼叫任何工具就回覆，且包含問號，幾乎必定是在反問
- 前端呈現只需要知道「這是不是最終答案」，不需要結構化的 clarification 內容

### Decision 5: 公開 private 函式 vs. 複製

**選擇：** 將 `_normalize_chart_data` / `_summarize_for_llm` 改名為公開函式（移除前綴底線）。

**替代方案：** 在新模組中複製實作。

**理由**：
- 避免邏輯重複和維護負擔
- 這些函式無副作用，公開不影響安全性
- 現有呼叫者（`process_query_function` / `process_query_text2sql`）不受影響

## Risks / Trade-offs

- **[Prompt-based parsing 不穩定]** → gpt-oss:120b 的 `<tool_call>` 格式遵循率未知。**Mitigation**：JSON parse 失敗時跳過該 tool_call 繼續迴圈；回應完全無法解析時退化為直接回覆文字。實作前先用 20 個測試 prompt 驗證。

- **[迴圈打轉]** → LLM 可能反覆呼叫同一工具或在工具間打轉。**Mitigation**：同工具+同參數不重複呼叫；max 5 rounds 強制終止。

- **[延遲不可預測]** → 1~5 輪 LLM 呼叫 + 工具執行，最差可達 5×(LLM timeout + 工具 timeout)。**Mitigation**：前端已有三階段 loading 動畫；tool_trace 即時回傳讓使用者看到進度。

- **[結果截斷資訊遺失]** → 工具結果摘要截斷為 ~1500 chars 餵給下輪 LLM，可能遺失關鍵數據。**Mitigation**：`summarize_for_llm` 按 chart_type 智慧截斷（保留 top N + 統計值），已驗證覆蓋主要場景。

- **[Tier 1 工具選擇偏差]** → 常駐工具可能讓 LLM 偏向使用這些工具而忽略更合適的 Tier 2 工具。**Mitigation**：system prompt 明確指示「如果常駐工具無法滿足需求，使用 search_tools 搜尋更多工具」。
