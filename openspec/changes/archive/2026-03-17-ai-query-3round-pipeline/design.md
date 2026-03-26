## Context

AI 助手 Phase 2（`ai-assisted-reporting` change）已完成，使用 gpt-oss:120b（16K context, OpenAI-compatible API）。實測發現兩個核心問題：(1) LLM 只做意圖解析，查詢結果直接給前端但無文字解讀；(2) 函式註冊表 16 個函式已接近單次 prompt 的合理上限，擴展困難。同時 Redis 多輪對話管理帶來的複雜度遠超其價值（使用者幾乎不追問上文）。

LLM 環境不變：`https://ollama_pjapi.theaken.com/v1/chat/completions`，model `gpt-oss:120b`，16,384 tokens context，`verify=False`（TLS hostname mismatch），~25ms/token。

## Goals / Non-Goals

**Goals:**
- G1: 查詢結果附帶自然語言摘要（如「Hold 最多的站別是焊接_WB，152 批」）
- G2: 將 prompt 拆為三輪以支撐 100+ 函式（Round 1 精簡列表、Round 2 單函式 schema、Round 3 結果摘要）
- G3: 函式註冊表遷移到 YAML，非開發者也能新增函式
- G4: 移除 Redis 對話管理，每次提問完全獨立
- G5: 前端分步載入動畫 + 對話分隔線

**Non-Goals:**
- 不支援追問上文（如「上面那個改看焊接站」）— 每次獨立查詢
- 不實作 SSE / WebSocket streaming — 仍為同步 HTTP 請求
- 不新增更多函式到 YAML — 本次只遷移現有 16 個，擴展是後續工作
- 不實作 Semantic Layer 或 Text-to-SQL — 維持 Function Calling 架構

## Decisions

### D1: 三輪 internal LLM pipeline（每次使用者提問 = 3 次 LLM 呼叫）

每次使用者發一個問題，後端依序呼叫 LLM 三次：

| Round | System Prompt | User Message | LLM 輸出 | max_tokens | ~延遲 |
|-------|-------------|-------------|---------|-----------|------|
| R1 意圖分類 | 精簡函式目錄（名稱+描述，~400 tokens） | 使用者原始問題 | `{"function":"wip_matrix","explanation":"..."}` | 200 | ~2.5s |
| R2 參數填充 | 單一函式完整 schema + enum（~500 tokens） | 使用者原始問題 | `{"params":{"status":"HOLD"}}` | 300 | ~2.5s |
| R3 結果摘要 | 固定分析指引（~200 tokens） | 問題 + 查詢結果截斷文字 | 自然語言分析（3-5 句） | 500 | ~3s |

三輪都是獨立 LLM 呼叫，不帶對話歷史。Round 1 + 2 用小 max_tokens 降低延遲。

Round 3 fallback：若 LLM 呼叫失敗，回傳 `"查詢完成，請參考圖表。"` + chart_data 照常顯示。

### D2: YAML 函式註冊表

`src/mes_dashboard/services/ai_functions.yaml`，啟動時由 `ai_function_registry.py` 載入。

YAML 結構：
```yaml
_enums:
  WORKCENTER_GROUPS: [切割, 焊接_DB, ...]

reject_reason_pareto:
  description: 不良原因排行
  service: mes_dashboard.services.reject_history_service.query_reason_pareto
  chart_type: pareto
  params:
    workcenter_groups:
      type: list[string]
      required: false
      enum: $WORKCENTER_GROUPS
      description: 站別代碼列表
    ...
  drill_down: [reject_trend, reject_lot_list]
```

`$WORKCENTER_GROUPS` 引用在載入時展開。新增函式 = 編輯 YAML → 重啟服務。

### D3: 結果截斷策略（Round 3 送給 LLM 的資料）

Token 預算：Round 3 context 16K 中，system ~200 + user question ~100 + response 500 = 只用 800 → 可給結果 ~3,000 tokens（~4,500 chars）。

| chart_type | 截斷策略 |
|-----------|---------|
| pareto | 完整（通常 10-20 項） |
| trend | >30 筆 → 前 5 + 後 5 + min/max/avg 統計 |
| heatmap | Top-10 cells by value + 軸標籤 + 合計 |
| kpi | 完整（很小） |
| table | 前 10 列 × 5 重要欄位 + `"共 N 筆"` |
| fallback | `json.dumps[:4500] + "...(截斷)"` |

### D4: 移除 Redis 對話管理

移除：`_get_conversation`、`_save_conversation`、`_conversation_key`、`_new_conversation_id`、`_estimate_tokens`、OverflowError 邏輯。

`process_query(question: str)` 簡化為只接收 question。Route 不再解析 conversation_id 或 user_id。

Settings 移除：`AI_MAX_ROUNDS`、`AI_CONTEXT_TOKEN_LIMIT`、`AI_CONVERSATION_TTL`。

### D5: 前端 — 分步動畫 + 對話分隔

**分步動畫**（純客戶端計時器）：後端仍是單一 HTTP 請求，前端用 `setInterval` 每 3 秒切換步驟文字：
1. 「正在分析您的問題...」（0-3s，覆蓋 Round 1）
2. 「正在準備查詢...」（3-6s，覆蓋 Round 2 + service call）
3. 「正在生成報告...」（6s+，覆蓋 Round 3）

**對話分隔線**：每組 user+ai 訊息之間插入淡色分隔線 + 「新的查詢」文字（類似 Slack 日期分隔線），使用 `text-text-muted` + `border-stroke-soft` token。

**Header 按鈕**：「新對話」→「清除紀錄」（只清前端 messages）。

### D6: 新依賴 — PyYAML

需要 `PyYAML` 來載入 YAML 註冊表。若尚未在 requirements 中，需加入。

## Risks / Trade-offs

| 風險 | 影響 | 緩解 |
|------|-----|------|
| 延遲從 ~3s 增加到 ~8-12s | 使用者等待時間變長 | 分步動畫緩解感知；Round 1/2 用小 max_tokens 降延遲 |
| Round 3 摘要品質不穩定 | gpt-oss:120b 可能生成不精確的分析 | Fallback 機制：失敗時回 `"查詢完成，請參考圖表"` |
| 無法追問上文 | 使用者說「上面那個改看焊接站」無法處理 | 明確 UX 設計（對話分隔線）告知每次獨立；suggestion chips 提供後續查詢 |
| YAML 格式錯誤導致啟動失敗 | 服務無法啟動 | 載入時 validate schema + 清楚的 error log |
| Breaking API change | 前端必須同步更新 | 前後端同一 repo，同時部署 |
