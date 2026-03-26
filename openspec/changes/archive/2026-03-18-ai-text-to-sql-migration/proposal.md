## Why

目前 AI 查詢系統採用 3-round Function Call pipeline（Round1 選函式 → Round2 填參數 → 執行 → Round3 摘要），從 55 個預定義函式中選一個執行。實測 8 個真實使用者問題中有 6 個回答錯誤或無結果。根本原因：

1. **AI 不懂領域語言**：不認得設備 ID 格式（GWBK-0247）、工單號格式（GA26010001）、站別縮寫（WB=焊接_WB）
2. **AI 不懂資料源選擇**：無法判斷「目前」→ WIP 即時資料 vs「歷史」→ 歷史表
3. **Function registry 永遠追不上使用者問法的變化**：每種新查詢都要新增函式+service wrapper，維護成本高且覆蓋率低

改為 Text-to-SQL 架構後，AI 直接根據表 schema 和 SQL 範例生成查詢，徹底解除函式粒度限制。

## What Changes

### 新增

- **Text-to-SQL pipeline**：3-stage LLM 流程（分類領域 → 生成 SQL → 摘要結果），取代現有 3-round function call pipeline
- **Schema context 模組** (`ai_schema_context.py`)：從 `data/table_schema_info.json` + `sql/**/*.sql` 反推精簡表結構，為 LLM 提供表分組、欄位定義、few-shot SQL 範例
- **SQL 重試機制**：SQL 執行失敗時（ORA-xxxxx），將 Oracle 錯誤訊息回饋給 LLM 修正，最多重試 2 次
- **前端 SQL 顯示**：AI 回答下方可折疊查看生成的 SQL 語句和執行步驟
- **Schema 反推腳本** (`scripts/extract_sql_schema.py`)：開發工具，掃描 SQL 模板提取實際使用欄位

### 修改

- **`ai_query_service.py`**：新增 `process_query_text2sql()`，原有 `process_query()` 透過 `AI_MODE` 環境變數分流
- **`ai_function_registry.py`**：新增 `build_stage1_prompt()`（領域分類）和 `build_stage2_prompt(domains)`（SQL 生成）
- **`useAiChat.js`**：解析 `sql_used` 和 `tool_trace` 新欄位
- **`AiChatMessage.vue`**：新增可折疊 SQL 區塊和執行步驟顯示

### 決策：現有 Function Call 系統的處置

**保留但降級為 fallback**，理由如下：

| 選項 | 優點 | 缺點 | 決策 |
|------|------|------|------|
| **A. 完全移除** | 程式碼簡潔 | 無回退路徑；55 個函式+service 的測試覆蓋失效；已驗證的查詢品質丟失 | 否 |
| **B. 保留為預設，Text-to-SQL 為實驗** | 風險最低 | 永遠不會真正切換，Text-to-SQL 無法充分驗證 | 否 |
| **C. Text-to-SQL 為預設，Function Call 為 fallback** | 新架構充分驗證；舊系統仍可用；漸進式遷移 | 維護兩套 pipeline | **採用** |

具體做法：
- `AI_MODE=text2sql`（預設）→ 走 Text-to-SQL pipeline
- `AI_MODE=function` → 走原有 3-round pipeline（回退用）
- 穩定運行 1-2 個月後，評估是否移除 function pipeline
- **不刪除** `ai_functions.yaml`、`ai_function_registry.py` 等既有檔案，僅將 `process_query()` 原有邏輯改名為 `process_query_function()`

### 不變

- **API route** (`ai_routes.py`)：仍呼叫 `process_query()`，回應格式向下相容
- **DB 連線層** (`core/database.py`)：直接使用現有 `read_sql_df()` 含 55s timeout + circuit breaker
- **前端 API 呼叫**：POST `/api/ai/query` 不變，新增欄位為 additive（`sql_used`、`tool_trace`）
- **Rate limiting**：維持每 IP 3 requests / 60s
- **安全性**：DB 帳號本身為 read-only（SELECT only），無需額外 SQL 安全閘門

## Capabilities

### New Capabilities

- `ai-text-to-sql-pipeline`: Text-to-SQL 核心 pipeline — 3-stage LLM 流程（領域分類 → SQL 生成 → 結果摘要），含 SQL 執行失敗重試機制
- `ai-schema-context`: Schema context 管理 — 表領域分組、精簡 schema 產生、few-shot SQL 範例庫，為 LLM 提供結構化的資料庫知識
- `ai-chat-sql-display`: 前端 SQL 透明化顯示 — AI 回答中展示生成的 SQL 和執行軌跡

### Modified Capabilities

（無既有 spec 需修改，AI 功能為首次建立 spec）

## Impact

### 後端
- `services/ai_query_service.py` — 主要變更：新增 text2sql pipeline + feature flag 分流
- `services/ai_function_registry.py` — 新增 2 個 prompt builder 函式
- `services/ai_schema_context.py` — **新建**：表分組 + schema + SQL 範例
- `scripts/extract_sql_schema.py` — **新建**：開發工具

### 前端
- `frontend/src/shared-composables/useAiChat.js` — 解析新回應欄位
- `frontend/src/shared-ui/components/AiChatMessage.vue` — SQL 顯示 UI

### 參考資料（不修改）
- `data/table_schema_info.json` — schema 主要來源
- `sql/**/*.sql` — 89 個模板，反推欄位 + few-shot 範例
- `docs/MES_Database_Reference.md` — 中文註解補充
- `docs/Oracle_Authorized_Objects.md` — 22 個授權物件白名單

### API 相容性
- `/api/ai/query` 回應新增 `sql_used`（string|null）和 `tool_trace`（array）欄位，為 additive change，不影響現有前端
- `contract/api_inventory.md` 需更新 AI route 描述
