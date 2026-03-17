## Why

目前 AI 助手每次提問只做 1 次 LLM 呼叫，將全部 16 個函式完整參數塞入 system prompt。這導致：(1) LLM 只做意圖解析不解讀查詢結果，使用者看到圖表卻不知道答案；(2) 系統有 145 個 API 端點但 AI 只覆蓋 16 個（11%），每新增函式 prompt 更長；(3) 函式註冊表是 400 行 Python dict，維護門檻高；(4) Redis 多輪對話管理過度複雜但實際不需要 LLM 記住上文。

## What Changes

- **BREAKING**: 移除 Redis 多輪對話管理 — `conversation_id`、5 輪上限、context token 偵測全部移除。每次使用者提問完全獨立
- **BREAKING**: API `POST /api/ai/query` request body 移除 `conversation_id`；response 移除 `conversation_id`、`round`、`max_rounds`
- 每次使用者提問改為三輪內部 LLM 呼叫：Round 1 意圖分類 → Round 2 參數填充 → Round 3 結果摘要
- 函式註冊表從 Python dict 遷移到 YAML 設定檔（`ai_functions.yaml`），新增函式只需編輯 YAML
- 前端新增分步載入動畫（正在分析 → 正在查詢 → 正在生成報告）
- 前端新增對話分隔線，讓使用者知道每次是獨立查詢
- 前端「新對話」按鈕改為「清除紀錄」按鈕
- 移除 `settings.py` 中 `AI_MAX_ROUNDS`、`AI_CONTEXT_TOKEN_LIMIT`、`AI_CONVERSATION_TTL` 配置

## Capabilities

### New Capabilities
- `ai-3round-pipeline`: 三輪 LLM pipeline（意圖分類 → 參數填充 → 結果摘要），含 YAML 函式註冊表、結果截斷策略、Round 3 fallback 機制
- `ai-chat-frontend-v2`: AI 面板 v2 — 獨立問答模式、分步載入動畫、對話分隔線、清除紀錄

### Modified Capabilities
- `ai-query-interface`: **BREAKING** — 移除 Redis 對話管理、conversation_id、round/max_rounds；process_query 簽名簡化為只需 question；新增 _call_llm_text、_summarize_for_llm
- `ai-query-frontend`: **BREAKING** — 移除 conversationId/currentRound/maxRounds/isContextFull 狀態；移除 CONTEXT_LIMIT_REACHED 處理；canSubmit 簡化

## Impact

- **Backend**: `ai_function_registry.py`（YAML 載入 + 三個 prompt builder）、`ai_query_service.py`（三輪 pipeline 重構）、`ai_routes.py`（簡化）、`settings.py`（移除 3 項配置）
- **Frontend**: `useAiChat.js`、`AiChatPanel.vue`、`AiChatMessage.vue`、`App.vue`、`ai-chat.css`
- **新檔案**: `src/mes_dashboard/services/ai_functions.yaml`
- **新依賴**: PyYAML（需確認是否已有）
- **API**: `POST /api/ai/query` breaking change — 移除 conversation_id 輸入和對話狀態輸出
- **延遲**: 從 ~3s 增加到 ~8-12s（3 次 LLM 呼叫），但前端有分步動畫緩解感知
- **測試**: test_ai_function_registry.py、test_ai_query_service.py、test_ai_routes.py 需更新
- **合約**: `contract/api_inventory.md`、`.env.example` 需更新
